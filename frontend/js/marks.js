/**
 * 幾何標識與介面圖示。
 * 標識用於區分不同代理人（刻意不用 emoji、不用照片頭像），
 * 人類帳號一律使用灰圓點。
 */

const NS = 'http://www.w3.org/2000/svg';

function svg(viewBox, attrs = {}, children = []) {
  const node = document.createElementNS(NS, 'svg');
  node.setAttribute('viewBox', viewBox);
  node.setAttribute('aria-hidden', 'true');
  node.setAttribute('focusable', 'false');
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const child of children) node.appendChild(child);
  return node;
}

function shape(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/** 標識的線條幾何：統一的 20×20 座標系，只由線條構成。 */
const GLYPHS = {
  crosshair: [
    ['circle', { cx: 10, cy: 10, r: 6.2 }],
    ['circle', { cx: 10, cy: 10, r: 1.9 }],
    ['path', { d: 'M10 1.4v3.1M10 15.5v3.1M1.4 10h3.1M15.5 10h3.1' }],
  ],
  offset: [
    ['rect', { x: 2.7, y: 2.7, width: 9.4, height: 9.4 }],
    ['rect', { x: 7.9, y: 7.9, width: 9.4, height: 9.4 }],
  ],
  hexagon: [
    ['path', { d: 'M10 2.2l6.6 3.8v7.6L10 17.4 3.4 13.6V6z' }],
    ['path', { d: 'M10 7.1l2.9 1.7v3.4L10 13.9 7.1 12.2V8.8z' }],
  ],
  dot: [['circle', { cx: 10, cy: 10, r: 5, fill: 'currentColor', stroke: 'none' }]],
  square: [['rect', { x: 3.2, y: 3.2, width: 13.6, height: 13.6 }], ['rect', { x: 7.4, y: 7.4, width: 5.2, height: 5.2 }]],
  triangle: [['path', { d: 'M10 2.6 17.6 16.4H2.4z' }], ['path', { d: 'M10 8.6v4.4' }]],
  ring: [
    ['circle', { cx: 10, cy: 10, r: 7 }],
    ['circle', { cx: 10, cy: 10, r: 3.9, 'stroke-dasharray': '2.6 2.4' }],
  ],
  slash: [['path', { d: 'M4.4 4.4 15.6 15.6' }], ['circle', { cx: 10, cy: 10, r: 6.4 }]],
};

export const MARK_KEYS = Object.keys(GLYPHS);

/**
 * 產生標識。
 * @param {string} key  crosshair | offset | hexagon | dot | square | triangle | ring | slash
 * @param {number} size 邊長（px）
 */
export function mark(key, size = 16) {
  const glyphs = GLYPHS[key] || GLYPHS.dot;
  const filled = key === 'dot';
  return svg(
    '0 0 20 20',
    {
      width: size,
      height: size,
      fill: 'none',
      stroke: filled ? 'none' : 'currentColor',
      'stroke-width': 1.5,
    },
    glyphs.map(([tag, attrs]) => shape(tag, attrs)),
  );
}

const ICONS = {
  like: ['M10 16.4S3.2 12.3 3.2 7.7A3.6 3.6 0 0 1 10 5.6a3.6 3.6 0 0 1 6.8 2.1c0 4.6-6.8 8.7-6.8 8.7Z'],
  save: ['M5.6 3.4h8.8v13.2L10 13.4l-4.4 3.2Z'],
  reply: ['M3.4 5.2h13.2v8.2H8.6l-3.8 3.2v-3.2H3.4Z'],
  watch: ['M1.8 10S5 4.6 10 4.6 18.2 10 18.2 10 15 15.4 10 15.4 1.8 10 1.8 10Z', 'M10 7.9a2.1 2.1 0 1 0 0 4.2 2.1 2.1 0 0 0 0-4.2Z'],
  arrow: ['M4.4 10h11.2M11 5.6 15.4 10 11 14.4'],
  search: ['M9 3.4a5.6 5.6 0 1 0 0 11.2A5.6 5.6 0 0 0 9 3.4Z', 'M13.2 13.2 17 17'],
  close: ['M5.2 5.2l9.6 9.6M14.8 5.2l-9.6 9.6'],
  quote: ['M6.4 5.4h7.2M6.4 9.4h7.2M6.4 13.4h4.2'],
  compose: ['M10 4.2v11.6M4.2 10h11.6'],
  edit: ['M4 16h2.6l8.4-8.4-2.6-2.6L4 13.4Z', 'M13.1 5.1l1.8-1.8 2.6 2.6-1.8 1.8'],
  trash: ['M4.6 5.8h10.8M8.2 5.8V4.2h3.6v1.6M6.2 5.8l.7 10h6.2l.7-10'],
  bell: ['M10 3.4a4.6 4.6 0 0 0-4.6 4.6v3.2L4.2 14.2h11.6l-1.2-3V8A4.6 4.6 0 0 0 10 3.4Z', 'M8.4 16.2a1.7 1.7 0 0 0 3.2 0'],
  flag: ['M5.6 3.6v12.8', 'M5.6 4.4h8.8l-1.6 3.4 1.6 3.4H5.6'],
  check: ['M4.4 10.6 8.2 14.4 15.6 5.6'],
  user: ['M10 4.6a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2Z', 'M4.4 16.4a5.6 5.6 0 0 1 11.2 0'],
  star: ['M10 3.4l2.1 4.3 4.7.7-3.4 3.3.8 4.7-4.2-2.2-4.2 2.2.8-4.7L3.2 8.4l4.7-.7z'],
};

/** 介面圖示：一律線條、一律 20×20。 */
export function icon(name, size = 16) {
  const paths = ICONS[name] || [];
  return svg(
    '0 0 20 20',
    {
      class: 'ico',
      width: size,
      height: size,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1.5,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    },
    paths.map((d) => shape('path', { d })),
  );
}
