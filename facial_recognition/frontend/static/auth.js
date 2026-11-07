import { photograph } from './photos.js';
import {
  state,
  el,
  $,
  heading,
  panel,
  info,
  form,
  submit,
  group,
  button,
  link,
  notice,
  icon
} from './ui.js';
import {
  api,
  pendingMessage
} from './api.js';
let stream = null, cameraGeneration = 0, expiresAt = 0, biometricsMode = null;
export function stopCamera() {
  cameraGeneration++;
  if (stream)
    stream.getTracks().forEach(track => track.stop());
  stream = null;
  const video = $('video');
  if (video)
    video.srcObject = null;
  const capture = $('capture');
  if (capture)
    capture.disabled = true;
  const start = $('camera-start');
  if (start)
    start.disabled = false;
  const status = $('camera-state');
  if (status)
    status.textContent = 'Câmera desligada';
}
window.addEventListener('pagehide', stopCamera);
document.addEventListener('visibilitychange', () => {
  if (document.hidden)
    stopCamera();
});
export async function resume() {
  const flow = await api('/auth/flow', 'GET', null, { private: false });
  biometricsMode = flow.biometrics_mode;
  state.stage = flow.next_step;
  state.operation = flow.operation;
  expiresAt = Date.now() + flow.expires_in * 1000;
  return flow;
}
export async function advance(data) {
  stopCamera();
  state.dirty = false;
  if (data.next_step === 'SESSION') {
    state.stage = null;
    state.operation = null;
    state.user = await api('/auth/me', 'GET', null, { private: false });
    window.dispatchEvent(new Event('authenticated'));
  } else if (data.next_step === 'LOGIN') {
    state.stage = null;
    state.user = null;
    state.operation = null;
    location.hash = '#/login';
    window.dispatchEvent(new Event('render-page'));
    notice('Senha alterada. Entre novamente com sua nova senha.');
  } else {
    await resume();
    location.hash = '#/acesso';
    window.dispatchEvent(new Event('render-page'));
  }
}
export function loginView() {
  const f = form([
    {
      name: 'email',
      label: 'Email institucional',
      type: 'email',
      autocomplete: 'username',
      placeholder: 'nome@instituicao.exemplo…'
    },
    {
      name: 'password',
      label: 'Senha',
      type: 'password',
      max: 128,
      autocomplete: 'current-password'
    }
  ], {}, { track: false });
  submit(f, 'Entrar', async data => {
    const response = await api('/auth/login', 'POST', data, { private: false });
    f.controls.password.value = '';
    await advance(response);
  });
  return el('div', {
    class: 'auth-layout',
    'data-ui': ''
  }, el('section', { class: 'auth-context' }, el('div', { class: 'auth-story' }, el('h1', {}, 'Ciência que protege a vida.'), el('p', {}, 'Um espaço para investigar, colaborar e compartilhar conhecimento com responsabilidade.')), el('div', { class: 'auth-visual' }, photograph('anavilhanas', true)), el('div', { class: 'auth-context-bottom' }, el('span', {}, 'Fotografia ilustrativa · Biossegurança ambiental'), link('Consultar notícias públicas', '#/noticias'))), el('section', { class: 'panel login-card' }, el('div', {
    class: 'access-symbol',
    'aria-hidden': 'true'
  }, icon('samples')), el('h2', {}, 'Entre no laboratório'), el('p', {}, 'Acesse seu ambiente de pesquisa com sua conta institucional.'), f.node, info('Primeiro acesso?', 'Use a senha temporária entregue pelo administrador. Você será orientado nas próximas etapas.'), el('p', { class: 'login-help' }, 'Precisa recuperar o acesso? Procure o administrador. O cadastro é restrito a contas aprovadas.')));
}
export function passwordStart() {
  const f = form([{
      name: 'current_password',
      label: 'Senha atual',
      type: 'password',
      max: 128,
      autocomplete: 'current-password'
    }], {}, { track: false });
  const pending = pendingMessage('/auth/password-change/start', 'POST');
  submit(f, 'Confirmar senha atual', async data => advance(await api('/auth/password-change/start', 'POST', data)), { confirm: 'A troca de senha exigirá nova entrada e encerrará suas sessões. Continuar?' });
  return [
    heading('Alterar senha', 'Confirme sua senha atual para iniciar. A verificação facial será exigida quando aplicável.'),
    pending ? info('Pendente no backend', pending) : null,
    panel(f.node)
  ];
}
export function stageView() {
  if (!state.stage)
    return panel(el('h1', {}, 'Nenhuma etapa pendente'), link('Voltar ao login', '#/login'));
  const passwordChange = state.operation === 'PASSWORD_CHANGE';
  const status = el('p', {
    id: 'stage-expiry',
    class: 'muted'
  }, 'Esta etapa tem prazo limitado. Se expirar, entre novamente.');
  if (expiresAt)
    status.textContent = 'Etapa válida até ' + new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit'
    }).format(expiresAt) + '. Se expirar, entre novamente.';
  const cancel = button('Cancelar acesso', async () => {
    if (!window.confirm('Cancelar esta etapa e encerrar o contexto de acesso?') || state.busy)
      return;
    state.busy = true;
    try {
      await api('/auth/logout', 'POST', null, { private: false });
      state.stage = null;
      state.user = null;
      state.operation = null;
      state.dirty = false;
      stopCamera();
      location.hash = '#/login';
      window.dispatchEvent(new Event('render-page'));
    } catch (error) {
      notice(error.message, true);
    } finally {
      state.busy = false;
    }
  }, 'quiet');
  if (state.stage === 'CHANGE_PASSWORD') {
    const f = form([
      {
        name: 'new_password',
        label: 'Nova senha',
        type: 'password',
        minLength: 8,
        max: 128,
        autocomplete: 'new-password'
      },
      {
        name: 'password_confirmation',
        label: 'Confirme a nova senha',
        type: 'password',
        minLength: 8,
        max: 128,
        autocomplete: 'new-password'
      }
    ], {}, { track: false });
    submit(f, passwordChange ? 'Alterar senha e sair' : 'Concluir ativação', async data => {
      if (data.new_password !== data.password_confirmation)
        throw new Error('As duas senhas precisam ser iguais.');
      const response = await api(passwordChange ? '/auth/password-change/complete' : '/auth/password/complete', 'POST', data, { private: false });
      f.node.reset();
      await advance(response);
    });
    return [
      heading(passwordChange ? 'Definir nova senha' : 'Senha definitiva', 'Use entre 8 e 128 caracteres. Evite senhas comuns e escolha uma diferente da temporária.'),
      panel(status, f.node, cancel)
    ];
  }
  if (biometricsMode === 'simulated') {
    const proceed = button('Continuar sem câmera', async () => {
      if (state.busy)
        return;
      state.busy = true;
      proceed.disabled = true;
      try {
        await advance(await api('/auth/biometric/simulate', 'POST', null, { private: false }));
      } catch (error) {
        notice(error.message, true);
      } finally {
        state.busy = false;
        proceed.disabled = false;
      }
    }, 'primary');
    return [
      heading('Biometria simulada', 'Ambiente de desenvolvimento — nenhuma identidade facial será verificada.'),
      panel(status, info('Sem câmera', 'A senha e as permissões continuam sendo verificadas pelo servidor.'), proceed, cancel)
    ];
  }
  const enroll = state.stage === 'ENROLL_FACE';
  const video = el('video', {
    id: 'video',
    autoplay: true,
    muted: true,
    playsInline: true,
    'aria-label': 'Prévia da câmera',
    'aria-describedby': 'camera-instructions camera-state'
  });
  const cameraStatus = el('p', {
    id: 'camera-state',
    role: 'status'
  }, 'Câmera desligada');
  const progress = el('progress', {
    max: 5,
    value: 0,
    'aria-label': 'Imagens capturadas'
  });
  const capture = button('Capturar e verificar', async () => {
    if (!stream || state.busy)
      return;
    const generation = cameraGeneration;
    const capturedStream = stream;
    state.busy = true;
    capture.disabled = true;
    start.disabled = true;
    const f = new FormData();
    const canvas = document.createElement('canvas'), context = canvas.getContext('2d');
    progress.value = 0;
    const check = () => {
      if (generation !== cameraGeneration || capturedStream.getVideoTracks()[0]?.readyState !== 'live')
        throw new Error('A captura foi interrompida. Ligue a câmera para tentar novamente.');
    };
    try {
      for (let i = 0; i < 5; i++) {
        check();
        if (!video.videoWidth)
          throw new Error('Aguarde a imagem da câmera antes de capturar.');
        const scale = Math.min(1, 640 / video.videoWidth, 480 / video.videoHeight);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
        check();
        if (!blob)
          throw new Error('Não foi possível capturar a imagem. Tente novamente.');
        f.append('frames', blob, `capture-${ i }.jpg`);
        progress.value = i + 1;
        cameraStatus.textContent = `Capturando imagem ${ i + 1 } de 5. Mantenha o rosto centralizado.`;
        if (i < 4)
          await new Promise(resolve => setTimeout(resolve, 450));
      }
      check();
      cameraStatus.textContent = 'Verificando as imagens no servidor…';
      const data = await api(enroll ? '/auth/biometric/enroll' : '/auth/biometric', 'POST', f, { private: false });
      await advance(data);
    } catch (error) {
      cameraStatus.textContent = error.message;
      notice(error.message, true);
    } finally {
      state.busy = false;
      capture.disabled = !stream;
      start.disabled = Boolean(stream);
    }
  }, 'primary');
  capture.id = 'capture';
  capture.disabled = true;
  const start = button('Ligar câmera', async () => {
    if (state.busy)
      return;
    start.disabled = true;
    const generation = ++cameraGeneration;
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error('A câmera precisa de HTTPS ou localhost. A configuração de acesso remoto será feita separadamente.');
      const next = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user'
        },
        audio: false
      });
      if (generation !== cameraGeneration || !video.isConnected || document.hidden) {
        next.getTracks().forEach(t => t.stop());
        return;
      }
      stream = next;
      video.srcObject = stream;
      await video.play();
      stream.getVideoTracks()[0].onended = () => {
        stopCamera();
        cameraStatus.textContent = 'Câmera desconectada. Reconecte o dispositivo e tente novamente.';
      };
      capture.disabled = false;
      cameraStatus.textContent = 'Câmera ligada. Centralize o rosto antes de capturar.';
    } catch (error) {
      stopCamera();
      cameraStatus.textContent = error.name === 'NotAllowedError' ? 'Permissão negada. Autorize a câmera nas configurações do navegador.' : error.name === 'NotFoundError' ? 'Nenhuma câmera encontrada. Conecte uma webcam para continuar.' : error.message;
      notice(cameraStatus.textContent, true);
    } finally {
      start.disabled = Boolean(stream);
    }
  });
  start.id = 'camera-start';
  return [
    heading(enroll ? 'Cadastrar rosto' : 'Verificar identidade', 'Seu acesso só será liberado após a confirmação pelo servidor.'),
    el('div', { class: 'camera-layout' }, panel(status, el('p', { id: 'camera-instructions' }, 'Centralize o rosto, mantenha testa e queixo visíveis e procure boa iluminação.'), el('div', { class: 'camera' }, video, el('div', {
      class: 'face-guide',
      'aria-hidden': 'true'
    })), cameraStatus, progress, group(start, capture, button('Desligar câmera', stopCamera, 'quiet')), cancel), el('section', { class: 'camera-help' }, el('h2', {}, 'Antes de começar'), el('ul', {}, el('li', {}, 'Deixe somente uma pessoa no enquadramento.'), el('li', {}, 'Mantenha o rosto visível durante a captura.'), el('li', {}, 'Serão enviadas 5 imagens em aproximadamente 2 segundos.')), info('Sem webcam?', 'O simulador de biometria para desenvolvimento depende de uma implementação separada no backend. Esta interface não simula aprovação facial.'), el('p', {}, 'As imagens são processadas em memória. O experimento não comprova proteção contra todas as formas de fraude.')))
  ];
}
