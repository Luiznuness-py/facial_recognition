"""Configuração, redes e inferência do MiniFASNet usado na antifraude.

Arquiteturas e CropImage adaptados de Silent-Face-Anti-Spoofing, de Minivision.
Modificações: fontes reunidas, nomes ajustados e carregamento integrado à API.
Os dois pesos originais ficam em models/, separados do código Python.
"""
# Copyright 2020 Minivision. Autor original: zhuying.
# Licensed under the Apache License, Version 2.0.
# Texto completo em licenses/MiniFASNet-LICENSE.
from pathlib import Path

import cv2
import numpy as np
import torch
from torch.nn import (
    Linear, Conv2d, BatchNorm1d, BatchNorm2d, PReLU, ReLU, Sigmoid,
    AdaptiveAvgPool2d, Sequential, Module,
)

MODEL_DIR = Path(__file__).resolve().parents[2] / 'models'
INPUT_SIZE = (80, 80)
REAL_CLASS = 1


class Flatten(Module):
    """Transforma o conjunto de características de cada imagem em um vetor.

    Preserva o primeiro eixo como tamanho do lote e achata os demais. Não possui parâmetros
    treináveis.
    """

    def forward(self, input):
        """Propaga o tensor de entrada pelas camadas de Flatten.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            input: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Matriz com formato [lote, características achatadas].

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        return input.view(input.size(0), -1)


class Conv_block(Module):
    """Representa o bloco convolucional com normalização e ativação PReLU.

    É um componente da arquitetura original Minivision. Os nomes das camadas são preservados
    para carregar os state_dict dos pesos enviados.

    Attributes:
        conv: Convolução bidimensional sem bias.
        bn: Normalização por lote dos canais de saída.
        prelu: Ativação PReLU aplicada ao resultado normalizado.
    """

    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        """Inicializa as camadas de Conv_block com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            in_c: Quantidade de canais do tensor de entrada.
            out_c: Quantidade de canais produzidos pela convolução.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
            groups: Número de grupos da convolução; deve ser compatível com os canais.
        """
        super(Conv_block, self).__init__()
        self.conv = Conv2d(in_c, out_c, kernel_size=kernel, groups=groups,
                           stride=stride, padding=padding, bias=False)
        self.bn = BatchNorm2d(out_c)
        self.prelu = PReLU(out_c)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de Conv_block.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        x = self.conv(x)
        x = self.bn(x)
        x = self.prelu(x)
        return x


class Linear_block(Module):
    """Representa um bloco convolucional sem ativação final.

    Combina projeção convolucional e normalização por lote, conforme a arquitetura original;
    o nome linear não significa uma camada torch.nn.Linear.

    Attributes:
        conv: Convolução bidimensional sem bias.
        bn: Normalização dos canais projetados.
    """

    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        """Inicializa as camadas de Linear_block com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            in_c: Quantidade de canais do tensor de entrada.
            out_c: Quantidade de canais produzidos pela convolução.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
            groups: Número de grupos da convolução; deve ser compatível com os canais.
        """
        super(Linear_block, self).__init__()
        self.conv = Conv2d(in_c, out_channels=out_c, kernel_size=kernel,
                           groups=groups, stride=stride, padding=padding, bias=False)
        self.bn = BatchNorm2d(out_c)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de Linear_block.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        x = self.conv(x)
        x = self.bn(x)
        return x


class Depth_Wise(Module):
    """Combina expansão, convolução por canal e projeção de características.

    A ligação residual exige que entrada e projeção tenham formas compatíveis. O agrupamento
    efetivo da convolução por canal vem de c2, como no código original.

    Attributes:
        conv: Bloco de expansão pontual.
        conv_dw: Convolução agrupada por canal.
        project: Bloco de projeção sem ativação.
        residual: Indica se a entrada é somada à projeção.
    """

    def __init__(self, c1, c2, c3, residual=False, kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=1):
        """Inicializa as camadas de Depth_Wise com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            c1: Par ou sequência de pares de canais para a expansão pontual.
            c2: Par ou sequência de pares de canais para a convolução por canal.
            c3: Par ou sequência de pares de canais para a projeção final.
            residual: Habilita a soma da entrada ao resultado projetado.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
            groups: Parâmetro de agrupamento da arquitetura; nos blocos Depth_Wise, o
                agrupamento efetivo é definido pelos canais c2.
        """
        super(Depth_Wise, self).__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de Depth_Wise.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        if self.residual:
            short_cut = x
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if self.residual:
            output = short_cut + x
        else:
            output = x
        return output


class Residual(Module):
    """Encadeia os blocos residuais de um estágio da rede.

    Monta cada bloco com os canais definidos pelas listas c1, c2 e c3. As estruturas e os
    nomes são mantidos para compatibilidade dos pesos.

    Attributes:
        model: Sequência de blocos Depth_Wise com conexão residual.
    """

    def __init__(self, c1, c2, c3, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1)):
        """Inicializa as camadas de Residual com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            c1: Par ou sequência de pares de canais para a expansão pontual.
            c2: Par ou sequência de pares de canais para a convolução por canal.
            c3: Par ou sequência de pares de canais para a projeção final.
            num_block: Quantidade de blocos residuais deste estágio.
            groups: Parâmetro de agrupamento da arquitetura; nos blocos Depth_Wise, o
                agrupamento efetivo é definido pelos canais c2.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
        """
        super(Residual, self).__init__()
        modules = []
        for i in range(num_block):
            c1_tuple = c1[i]
            c2_tuple = c2[i]
            c3_tuple = c3[i]
            modules.append(Depth_Wise(c1_tuple, c2_tuple, c3_tuple, residual=True,
                                      kernel=kernel, padding=padding, stride=stride, groups=groups))
        self.model = Sequential(*modules)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de Residual.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        return self.model(x)


class SEModule(Module):
    """Calcula a atenção de canais pelo mecanismo squeeze-and-excitation.

    Resume espacialmente cada canal, reduz e expande a quantidade de canais e aplica pesos
    entre zero e um à entrada.

    Attributes:
        avg_pool: Média espacial adaptativa por canal.
        fc1, bn1, relu: Redução de canais, normalização e ativação.
        fc2, bn2, sigmoid: Expansão e cálculo dos pesos por canal.
    """

    def __init__(self, channels, reduction):
        """Inicializa as camadas de SEModule com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            channels: Número de canais cujo peso de atenção será calculado.
            reduction: Fator de redução temporária de canais no módulo SE.
        """
        super(SEModule, self).__init__()
        self.avg_pool = AdaptiveAvgPool2d(1)
        self.fc1 = Conv2d(
            channels, channels // reduction, kernel_size=1, padding=0, bias=False)
        self.bn1 = BatchNorm2d(channels // reduction)
        self.relu = ReLU(inplace=True)
        self.fc2 = Conv2d(
            channels // reduction, channels, kernel_size=1, padding=0, bias=False)
        self.bn2 = BatchNorm2d(channels)
        self.sigmoid = Sigmoid()

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de SEModule.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características ponderadas com a mesma forma da entrada.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        module_input = x
        x = self.avg_pool(x)
        x = self.fc1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.fc2(x)
        x = self.bn2(x)
        x = self.sigmoid(x)
        return module_input * x


class ResidualSE(Module):
    """Encadeia blocos residuais com atenção no último bloco do estágio.

    Os primeiros blocos usam Depth_Wise; o último usa Depth_Wise_SE. Essa disposição
    reproduz a arquitetura da variante SE enviada.

    Attributes:
        model: Sequência de blocos residuais, com atenção no último.
    """

    def __init__(self, c1, c2, c3, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1), se_reduct=4):
        """Inicializa as camadas de ResidualSE com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            c1: Par ou sequência de pares de canais para a expansão pontual.
            c2: Par ou sequência de pares de canais para a convolução por canal.
            c3: Par ou sequência de pares de canais para a projeção final.
            num_block: Quantidade de blocos residuais deste estágio.
            groups: Parâmetro de agrupamento da arquitetura; nos blocos Depth_Wise, o
                agrupamento efetivo é definido pelos canais c2.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
            se_reduct: Fator de redução dos canais no módulo de atenção.
        """
        super(ResidualSE, self).__init__()
        modules = []
        for i in range(num_block):
            c1_tuple = c1[i]
            c2_tuple = c2[i]
            c3_tuple = c3[i]
            if i == num_block-1:
                modules.append(
                    Depth_Wise_SE(c1_tuple, c2_tuple, c3_tuple, residual=True, kernel=kernel, padding=padding, stride=stride,
                               groups=groups, se_reduct=se_reduct))
            else:
                modules.append(Depth_Wise(c1_tuple, c2_tuple, c3_tuple, residual=True, kernel=kernel, padding=padding,
                                          stride=stride, groups=groups))
        self.model = Sequential(*modules)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de ResidualSE.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        return self.model(x)


class Depth_Wise_SE(Module):
    """Acrescenta atenção de canais ao bloco residual de convolução por canal.

    O módulo SE é aplicado no caminho residual antes da soma com a entrada. Com
    residual=False, devolve apenas a projeção, conforme a implementação original.

    Attributes:
        conv, conv_dw, project: Blocos de expansão, convolução por canal e projeção.
        residual: Habilita o atalho de soma com a entrada.
        se_module: Módulo de atenção dos canais projetados.
    """

    def __init__(self, c1, c2, c3, residual=False, kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=1, se_reduct=8):
        """Inicializa as camadas de Depth_Wise_SE com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            c1: Par ou sequência de pares de canais para a expansão pontual.
            c2: Par ou sequência de pares de canais para a convolução por canal.
            c3: Par ou sequência de pares de canais para a projeção final.
            residual: Habilita a soma da entrada ao resultado projetado.
            kernel: Dimensões do filtro convolucional em pixels.
            stride: Passo espacial usado pela convolução.
            padding: Preenchimento aplicado às bordas da entrada.
            groups: Parâmetro de agrupamento da arquitetura; nos blocos Depth_Wise, o
                agrupamento efetivo é definido pelos canais c2.
            se_reduct: Fator de redução dos canais no módulo de atenção.
        """
        super(Depth_Wise_SE, self).__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual
        self.se_module = SEModule(c3_out, se_reduct)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de Depth_Wise_SE.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Características transformadas pelo bloco, mantendo o eixo de lote.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        if self.residual:
            short_cut = x
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if self.residual:
            x = self.se_module(x)
            output = short_cut + x
        else:
            output = x
        return output


class MiniFASNetModel(Module):
    """Define a rede base de classificação antifraude compatível com os pesos .pth.

    Produz logits, não probabilidades. A aplicação calcula softmax e combina os dois modelos
    depois de carregar os pesos e colocá-los em avaliação.

    Attributes:
        embedding_size: Tamanho do vetor intermediário antes da classificação.
        conv1, conv2_dw: Blocos iniciais de extração de características.
        conv_23, conv_34, conv_45: Transições entre estágios.
        conv_3, conv_4, conv_5: Estágios de blocos residuais.
        conv_6_sep, conv_6_dw, conv_6_flatten: Projeção final e transformação em vetor.
        linear: Projeção para embedding_size quando diferente de 512.
        bn, drop, prob: Normalização, dropout e camada de logits das classes.
    """

    def __init__(self, keep, embedding_size, conv6_kernel=(7, 7),
                 drop_p=0.0, num_classes=3, img_channel=3):
        """Inicializa as camadas de MiniFASNetModel com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            keep: Lista de larguras dos canais preservados pela arquitetura do fornecedor.
            embedding_size: Tamanho do vetor intermediário anterior à camada de
                classificação.
            conv6_kernel: Filtro da convolução espacial final; a bancada usa (5, 5) para
                entrada 80 × 80.
            drop_p: Probabilidade de dropout durante treino; model.eval desativa o dropout
                na inferência.
            num_classes: Quantidade de logits de classificação produzidos pela rede.
            img_channel: Quantidade de canais da imagem de entrada; os pesos usados recebem
                três canais BGR.
        """
        super(MiniFASNetModel, self).__init__()
        self.embedding_size = embedding_size

        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[1])

        c1 = [(keep[1], keep[2])]
        c2 = [(keep[2], keep[3])]
        c3 = [(keep[3], keep[4])]

        self.conv_23 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]

        self.conv_3 = Residual(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[16], keep[17])]
        c2 = [(keep[17], keep[18])]
        c3 = [(keep[18], keep[19])]

        self.conv_34 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[19])

        c1 = [(keep[19], keep[20]), (keep[22], keep[23]), (keep[25], keep[26]), (keep[28], keep[29]),
              (keep[31], keep[32]), (keep[34], keep[35])]
        c2 = [(keep[20], keep[21]), (keep[23], keep[24]), (keep[26], keep[27]), (keep[29], keep[30]),
              (keep[32], keep[33]), (keep[35], keep[36])]
        c3 = [(keep[21], keep[22]), (keep[24], keep[25]), (keep[27], keep[28]), (keep[30], keep[31]),
              (keep[33], keep[34]), (keep[36], keep[37])]

        self.conv_4 = Residual(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[37], keep[38])]
        c2 = [(keep[38], keep[39])]
        c3 = [(keep[39], keep[40])]

        self.conv_45 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[40])

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]

        self.conv_5 = Residual(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_6_sep = Conv_block(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = Linear_block(keep[47], keep[48], groups=keep[48], kernel=conv6_kernel, stride=(1, 1), padding=(0, 0))
        self.conv_6_flatten = Flatten()
        self.linear = Linear(512, embedding_size, bias=False)
        self.bn = BatchNorm1d(embedding_size)
        self.drop = torch.nn.Dropout(p=drop_p)
        self.prob = Linear(embedding_size, num_classes, bias=False)

    def forward(self, x):
        """Propaga o tensor de entrada pelas camadas de MiniFASNetModel.

        O PyTorch chama este método ao executar a instância como função. Durante a bancada,
        a rede está em modo de avaliação e dentro de torch.inference_mode.

        Args:
            x: Tensor PyTorch com lote e dimensões compatíveis com as camadas; blocos
                convolucionais recebem [N, C, H, W].

        Returns:
            torch.Tensor: Logits com formato [lote, num_classes], ainda sem softmax.

        Raises:
            RuntimeError: Quando forma, canais, dispositivo ou tipo são incompatíveis com a
                rede.
        """
        out = self.conv1(x)
        out = self.conv2_dw(out)
        out = self.conv_23(out)
        out = self.conv_3(out)
        out = self.conv_34(out)
        out = self.conv_4(out)
        out = self.conv_45(out)
        out = self.conv_5(out)
        out = self.conv_6_sep(out)
        out = self.conv_6_dw(out)
        out = self.conv_6_flatten(out)
        if self.embedding_size != 512:
            out = self.linear(out)
        out = self.bn(out)
        out = self.drop(out)
        out = self.prob(out)
        return out


class MiniFASNetSE(MiniFASNetModel):
    """Especializa a rede base com atenção de canais nos estágios residuais.

    Herda o restante da estrutura de MiniFASNetModel e substitui os estágios 3, 4 e 5 por
    ResidualSE. Os pesos usados pela aplicação têm três classes.

    Attributes:
        conv_3, conv_4, conv_5: Estágios com atenção de canais; os demais atributos são
            herdados.
    """

    def __init__(self, keep, embedding_size, conv6_kernel=(7, 7),drop_p=0.75, num_classes=4, img_channel=3):
        """Inicializa as camadas de MiniFASNetSE com a estrutura dos pesos originais.

        Registra as camadas como submódulos PyTorch. A criação da rede não carrega pesos nem
        executa inferência.

        Args:
            keep: Lista de larguras dos canais preservados pela arquitetura do fornecedor.
            embedding_size: Tamanho do vetor intermediário anterior à camada de
                classificação.
            conv6_kernel: Filtro da convolução espacial final; a bancada usa (5, 5) para
                entrada 80 × 80.
            drop_p: Probabilidade de dropout durante treino; model.eval desativa o dropout
                na inferência.
            num_classes: Quantidade de logits de classificação produzidos pela rede.
            img_channel: Quantidade de canais da imagem de entrada; os pesos usados recebem
                três canais BGR.
        """
        super(MiniFASNetSE, self).__init__(keep=keep, embedding_size=embedding_size, conv6_kernel=conv6_kernel,
                                               drop_p=drop_p, num_classes=num_classes, img_channel=img_channel)

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]

        self.conv_3 = ResidualSE(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[19], keep[20]), (keep[22], keep[23]), (keep[25], keep[26]), (keep[28], keep[29]),
              (keep[31], keep[32]), (keep[34], keep[35])]
        c2 = [(keep[20], keep[21]), (keep[23], keep[24]), (keep[26], keep[27]), (keep[29], keep[30]),
              (keep[32], keep[33]), (keep[35], keep[36])]
        c3 = [(keep[21], keep[22]), (keep[24], keep[25]), (keep[27], keep[28]), (keep[30], keep[31]),
              (keep[33], keep[34]), (keep[36], keep[37])]

        self.conv_4 = ResidualSE(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]
        self.conv_5 = ResidualSE(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))



keep_dict = {'1.8M': [32, 32, 103, 103, 64, 13, 13, 64, 26, 26,
                      64, 13, 13, 64, 52, 52, 64, 231, 231, 128,
                      154, 154, 128, 52, 52, 128, 26, 26, 128, 52,
                      52, 128, 26, 26, 128, 26, 26, 128, 308, 308,
                      128, 26, 26, 128, 26, 26, 128, 512, 512],

             '1.8M_': [32, 32, 103, 103, 64, 13, 13, 64, 13, 13, 64, 13,
                       13, 64, 13, 13, 64, 231, 231, 128, 231, 231, 128, 52,
                       52, 128, 26, 26, 128, 77, 77, 128, 26, 26, 128, 26, 26,
                       128, 308, 308, 128, 26, 26, 128, 26, 26, 128, 512, 512]
             }


# (80x80) flops: 0.044, params: 0.41


# (80x80) flops: 0.044, params: 0.43
def MiniFASNetV2(embedding_size=128, conv6_kernel=(7, 7),
                     drop_p=0.2, num_classes=3, img_channel=3):
    """Constrói a variante MiniFASNetV2 com os canais originais do modelo.

    A classe de integração chama esta fábrica, carrega o state_dict correspondente e ativa o
    modo eval antes da primeira inferência.

    Args:
        embedding_size: Tamanho do vetor intermediário anterior à camada de classificação.
        conv6_kernel: Filtro da convolução espacial final; a bancada usa (5, 5) para entrada
            80 × 80.
        drop_p: Probabilidade de dropout durante treino; model.eval desativa o dropout na
            inferência.
        num_classes: Quantidade de logits de classificação produzidos pela rede.
        img_channel: Quantidade de canais da imagem de entrada; os pesos usados recebem três
            canais BGR.

    Returns:
        torch.nn.Module: Rede inicializada, ainda sem pesos treinados carregados.
    """
    return MiniFASNetModel(keep_dict['1.8M_'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)

def MiniFASNetV1SE(embedding_size=128, conv6_kernel=(7, 7),
                   drop_p=0.75, num_classes=3, img_channel=3):
    """Constrói a variante MiniFASNetV1SE com os canais originais do modelo.

    A classe de integração chama esta fábrica, carrega o state_dict correspondente e ativa o
    modo eval antes da primeira inferência.

    Args:
        embedding_size: Tamanho do vetor intermediário anterior à camada de classificação.
        conv6_kernel: Filtro da convolução espacial final; a bancada usa (5, 5) para entrada
            80 × 80.
        drop_p: Probabilidade de dropout durante treino; model.eval desativa o dropout na
            inferência.
        num_classes: Quantidade de logits de classificação produzidos pela rede.
        img_channel: Quantidade de canais da imagem de entrada; os pesos usados recebem três
            canais BGR.

    Returns:
        torch.nn.Module: Rede inicializada, ainda sem pesos treinados carregados.
    """
    return MiniFASNetSE(keep_dict['1.8M'], embedding_size, conv6_kernel,drop_p, num_classes, img_channel)

# (80x80) flops: 0.044, params: 0.43


class CropImage:
    """Amplia e recorta a caixa facial usando a regra original do fornecedor.

    Mantém o recorte dentro da imagem e redimensiona para o tamanho esperado pela rede. Não
    detecta rostos nem valida sua qualidade; recebe uma caixa já conferida pelo coordenador.
    """

    @staticmethod
    def _get_new_box(src_w, src_h, bbox, scale):
        """Calcula a caixa ampliada e desloca suas bordas para dentro da imagem.

        Reproduz o arredondamento e o deslocamento usados pelo fornecedor. A leitura do
        recorte soma um aos limites direito e inferior.

        Args:
            src_w: Largura da imagem original em pixels.
            src_h: Altura da imagem original em pixels.
            bbox: Caixa [x, y, largura, altura] com dimensões positivas.
            scale: Fator desejado de ampliação; é limitado ao tamanho disponível.

        Returns:
            tuple[int, int, int, int]: Limites esquerdo, superior, direito e inferior
                inclusivos.
        """
        x = bbox[0]
        y = bbox[1]
        box_w = bbox[2]
        box_h = bbox[3]

        scale = min((src_h-1)/box_h, min((src_w-1)/box_w, scale))

        new_width = box_w * scale
        new_height = box_h * scale
        center_x, center_y = box_w/2+x, box_h/2+y

        left_top_x = center_x-new_width/2
        left_top_y = center_y-new_height/2
        right_bottom_x = center_x+new_width/2
        right_bottom_y = center_y+new_height/2

        if left_top_x < 0:
            right_bottom_x -= left_top_x
            left_top_x = 0

        if left_top_y < 0:
            right_bottom_y -= left_top_y
            left_top_y = 0

        if right_bottom_x > src_w-1:
            left_top_x -= right_bottom_x-src_w+1
            right_bottom_x = src_w-1

        if right_bottom_y > src_h-1:
            left_top_y -= right_bottom_y-src_h+1
            right_bottom_y = src_h-1

        return int(left_top_x), int(left_top_y),\
               int(right_bottom_x), int(right_bottom_y)

    def crop(self, org_img, bbox, scale, out_w, out_h, crop=True):

        """Recorta a região facial e a redimensiona para a entrada da rede.

        Args:
            org_img: Imagem BGR original, com três canais.
            bbox: Caixa facial [x, y, largura, altura] previamente validada.
            scale: Fator de ampliação da região facial.
            out_w: Largura desejada para a entrada do modelo.
            out_h: Altura desejada para a entrada do modelo.
            crop: True para recortar a caixa ampliada; False para redimensionar a imagem
                inteira.

        Returns:
            numpy.ndarray: Recorte BGR no tamanho [out_h, out_w, 3].

        Raises:
            cv2.error: Quando o recorte ou as dimensões não podem ser processados.
        """
        if not crop:
            dst_img = cv2.resize(org_img, (out_w, out_h))
        else:
            src_h, src_w, _ = np.shape(org_img)
            left_top_x, left_top_y, \
                right_bottom_x, right_bottom_y = self._get_new_box(src_w, src_h, bbox, scale)

            img = org_img[left_top_y: right_bottom_y+1,
                          left_top_x: right_bottom_x+1]
            dst_img = cv2.resize(img, (out_w, out_h))
        return dst_img


class MiniFASNet:
    """Carrega os dois classificadores e combina a decisão antifraude de um rosto.

    Concentra pesos, arquiteturas, recorte e inferência no mesmo módulo. FaceModels controla
    o carregamento e serializa o uso; a identidade e as etapas de autenticação ficam fora
    desta classe.

    Attributes:
        models: Tuplas com rede em avaliação, altura, largura e escala de recorte.
        cropper: Instância de CropImage criada em load.
    """

    def __init__(self):
        """Prepara a lista de classificadores sem ler os arquivos de pesos.

        load deve ser chamado antes da primeira avaliação. O coordenador da aplicação é
        responsável por essa inicialização e pelo controle de concorrência.
        """
        self.models = []

    def load(self) -> None:
        """Carrega as variantes V2 e V1SE em CPU com os pesos locais da bancada.

        Usa INPUT_SIZE, as escalas 2.7/4.0, weights_only=True e remove o prefixo module. das
        chaves. A leitura é local, sem download automático; a inferência usa BGR em escala
        0..255.

        Returns:
            None: Inicializa cropper e preenche models com as duas redes em avaliação.

        Raises:
            OSError: Quando um arquivo .pth não está disponível.
            RuntimeError: Quando o state_dict não corresponde à arquitetura ou o
                carregamento falha.
        """
        torch.set_num_threads(2)
        self.cropper = CropImage()
        self.models = []
        height, width = INPUT_SIZE
        kernel = ((height + 15) // 16, (width + 15) // 16)
        configurations = [
            ('2.7_80x80_MiniFASNetV2.pth', MiniFASNetV2, 2.7),
            ('4_0_0_80x80_MiniFASNetV1SE.pth', MiniFASNetV1SE, 4.0),
        ]
        for filename, architecture, scale in configurations:
            model = architecture(conv6_kernel=kernel)
            weights = torch.load(MODEL_DIR / filename, map_location='cpu', weights_only=True)
            weights = {key.removeprefix('module.'): value for key, value in weights.items()}
            model.load_state_dict(weights)
            self.models.append((model.eval(), height, width, scale))

    def is_live(self, frame: np.ndarray, bbox: list[int]) -> bool:
        """Combina os classificadores para decidir se a face parece real.

        Pressupõe load concluído e acesso serializado pelo chamador. Avalia os dois recortes
        em inference_mode, preserva BGR/0..255 e soma as saídas softmax. A classificação não
        é um desafio ativo de prova de vida.

        Args:
            frame: Imagem BGR decodificada e validada pelo coordenador.
            bbox: Caixa do rosto [x, y, largura, altura] em pixels.

        Returns:
            bool: True se a soma das probabilidades escolhe REAL_CLASS=1; False para outra
                classe.

        Raises:
            cv2.error: Quando o recorte não pode ser redimensionado.
            RuntimeError: Quando a avaliação PyTorch recebe dados incompatíveis.
        """
        prediction = np.zeros(3)
        for model, height, width, scale in self.models:
            patch = self.cropper.crop(frame, bbox, scale, width, height, crop=scale is not None)
            # O ToTensor do fornecedor mantém BGR e os valores em 0..255.
            tensor = torch.from_numpy(patch.transpose(2, 0, 1).copy()).float().unsqueeze(0)
            with torch.inference_mode():
                prediction += torch.softmax(model(tensor), dim=1).numpy()[0]
        return int(prediction.argmax()) == REAL_CLASS
