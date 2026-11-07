import { el, link } from './ui.js';

const photos = {
  amazonia: {
    title: 'Rio Solimões · Amazônia brasileira',
    alt: 'Curvas do rio Solimões entre áreas de floresta amazônica, vistas do alto.',
    height: 786, author: 'lubasi', license: 'CC BY-SA 2.0', licensePath: 'by-sa/2.0',
    source: 'Aerial_view_of_the_Amazon_Rainforest.jpg'
  },
  tucano: {
    title: 'Tucano-toco · Ramphastos toco',
    alt: 'Tucano-toco de perfil, com o bico alaranjado visível por inteiro.',
    height: 753, author: 'AntanO', license: 'CC BY-SA 4.0', licensePath: 'by-sa/4.0',
    source: 'Toco_toucan_(Ramphastos_toco)_close-up.jpg'
  },
  anavilhanas: {
    title: 'Arquipélago de Anavilhanas · Amazonas',
    alt: 'Ilhas florestadas de Anavilhanas entre os canais do rio Negro.',
    height: 859, author: 'Jason Auch', license: 'CC BY 2.0', licensePath: 'by/2.0',
    source: 'Anavilhanas2.jpg'
  },
  'mata-atlantica': {
    title: 'Serra do Mar · Mata Atlântica',
    alt: 'Montanhas da Serra do Mar cobertas pela Mata Atlântica, com uma árvore em primeiro plano.',
    height: 960, author: 'Naná Voitille', license: 'CC BY-SA 3.0', licensePath: 'by-sa/3.0',
    source: 'Serra_do_Mar_-_Mata_Atlântica.jpg'
  }
};

/**
 * Monta uma fotografia responsiva com dimensões de origem e atribuição visível.
 * @param {string} name Chave de uma das fotografias ilustrativas aprovadas.
 * @param {boolean} priority Se true, prioriza a imagem principal; demais usam lazy loading.
 * @returns {HTMLElement} Figure com imagem local, legenda, autor, fonte e licença.
 */
export function photograph(name, priority = false) {
  const photo = photos[name];
  return el('figure', { class: 'photograph photograph-' + name }, el('img', {
    src: `/static/assets/${name}-1280.webp`,
    srcset: `/static/assets/${name}-640.webp 640w, /static/assets/${name}-1280.webp 1280w`,
    sizes: '(max-width: 650px) calc(100vw - 40px), (max-width: 1100px) 48vw, 640px',
    width: 1280, height: photo.height, alt: photo.alt,
    loading: priority ? 'eager' : 'lazy', fetchPriority: priority ? 'high' : 'auto', decoding: 'async'
  }), el('figcaption', {}, el('span', {}, photo.title), el('span', { class: 'photo-attribution' },
    link(photo.author, 'https://commons.wikimedia.org/wiki/File:' + encodeURIComponent(photo.source)),
    ' · ', link(photo.license, 'https://creativecommons.org/licenses/' + photo.licensePath + '/'))));
}
