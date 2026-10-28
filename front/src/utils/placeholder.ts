/**
 * 图片资源生成器：把纯前端绘制的 SVG 转成 data URI，
 * 让「图片展示」能力在没有后端图床 / 外网素材时也能完整跑通。
 */

const FONT = "'Microsoft YaHei','PingFang SC','Hiragino Sans GB',sans-serif"

const escapeXml = (raw: string) =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')

export const svgToDataUri = (svg: string) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`

const AVATAR_PALETTES: Array<[string, string]> = [
  ['#6c4cf1', '#a78bfa'],
  ['#3b82f6', '#60d4f5'],
  ['#f59e0b', '#fbbf24'],
  ['#10b981', '#6ee7b7'],
  ['#ec4899', '#f9a8d4'],
  ['#6366f1', '#22d3ee'],
]

const hashSeed = (text: string) => {
  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 100000
  }
  return hash
}

/**
 * 生成姓名头像（图片形式，可用于 <img> / 头像组件）。
 * 中文取末字，英文取首字母，保证不同用户颜色稳定。
 */
export function avatarImage(name = '用户', seed?: number): string {
  const key = seed ?? hashSeed(name)
  const [from, to] = AVATAR_PALETTES[key % AVATAR_PALETTES.length]
  const isCn = /[\u4e00-\u9fa5]/.test(name)
  const label = (isCn ? name.slice(-1) : name.slice(0, 2).toUpperCase()) || 'U'
  const fontSize = label.length > 1 ? 34 : 38
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${from}"/>
      <stop offset="1" stop-color="${to}"/>
    </linearGradient>
  </defs>
  <rect width="96" height="96" rx="28" fill="url(#g)"/>
  <circle cx="76" cy="20" r="26" fill="#ffffff" opacity="0.12"/>
  <text x="48" y="49" text-anchor="middle" dominant-baseline="middle" font-family="${FONT}"
        font-size="${fontSize}" font-weight="600" fill="#ffffff">${escapeXml(label)}</text>
</svg>`
  return svgToDataUri(svg)
}

export interface PageImageOptions {
  title: string
  lines: string[]
  page: number
  total: number
  /** 命中即整行高亮的关键词 */
  highlights?: string[]
  /** 是否在页脚盖章 */
  stamped?: boolean
}

const PAGE_W = 720
const PAGE_H = 1018
const PAD_X = 66
const BODY_TOP = 168
const LINE_H = 26
const MAX_LINES = 28

/** 按每行字数硬折行，避免 SVG 文本溢出页面 */
export function wrapText(text: string, perLine = 30): string[] {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\t/g, ' ')
  const out: string[] = []
  normalized.split('\n').forEach((paragraph) => {
    const line = paragraph.trim()
    if (!line) {
      out.push('')
      return
    }
    for (let i = 0; i < line.length; i += perLine) {
      out.push(line.slice(i, i + perLine))
    }
  })
  return out
}

/** 生成一页合同扫描图（真实图片，可缩放 / 可预览大图） */
export function contractPageImage(options: PageImageOptions): string {
  const { title, lines, page, total, highlights = [], stamped = false } = options
  const visible = lines.slice(0, MAX_LINES)
  const body = visible
    .map((line, index) => {
      const y = BODY_TOP + index * LINE_H
      if (!line) return ''
      const hit = highlights.some((kw) => kw && line.includes(kw))
      const background = hit
        ? `<rect x="${PAD_X - 12}" y="${y - 17}" width="${PAGE_W - (PAD_X - 12) * 2}" height="${LINE_H - 2}" rx="4" fill="#fdf3d8"/>`
        : ''
      const bold = hit ? ' font-weight="600" fill="#8a5a00"' : ' fill="#3d4152"'
      return `${background}<text x="${PAD_X}" y="${y}" font-family="${FONT}" font-size="13"${bold}>${escapeXml(line)}</text>`
    })
    .join('')

  const stamp = stamped
    ? `<g transform="translate(548, 812) rotate(-14)" opacity="0.72">
        <circle r="58" fill="none" stroke="#d33b3b" stroke-width="3"/>
        <circle r="50" fill="none" stroke="#d33b3b" stroke-width="1.2"/>
        <text y="-6" text-anchor="middle" font-family="${FONT}" font-size="15" font-weight="700" fill="#d33b3b">合同专用章</text>
        <text y="16" text-anchor="middle" font-family="${FONT}" font-size="9" fill="#d33b3b">契智法务 · 电子签章</text>
      </g>`
    : ''

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${PAGE_W}" height="${PAGE_H}" viewBox="0 0 ${PAGE_W} ${PAGE_H}">
  <rect width="${PAGE_W}" height="${PAGE_H}" fill="#ffffff"/>
  <rect x="0.5" y="0.5" width="${PAGE_W - 1}" height="${PAGE_H - 1}" fill="none" stroke="#eceef6"/>
  <text x="${PAD_X}" y="46" font-family="${FONT}" font-size="10" fill="#a3a8ba" letter-spacing="1">契智 · 合同原文</text>
  <text x="${PAGE_W - PAD_X}" y="46" text-anchor="end" font-family="${FONT}" font-size="10" fill="#a3a8ba">第 ${page} / ${total} 页</text>
  <line x1="${PAD_X}" y1="58" x2="${PAGE_W - PAD_X}" y2="58" stroke="#eee9fb" stroke-width="1"/>
  <text x="${PAGE_W / 2}" y="112" text-anchor="middle" font-family="${FONT}" font-size="19" font-weight="700" fill="#1b1d2e">${escapeXml(title)}</text>
  <line x1="${PAGE_W / 2 - 26}" y1="128" x2="${PAGE_W / 2 + 26}" y2="128" stroke="#6c4cf1" stroke-width="2" stroke-linecap="round"/>
  ${body}
  ${stamp}
  <text x="${PAGE_W / 2}" y="${PAGE_H - 34}" text-anchor="middle" font-family="${FONT}" font-size="10" fill="#b3b8c8">${page} / ${total}</text>
</svg>`
  return svgToDataUri(svg)
}

/** 知识库资料封面：不同分类不同配色，用于列表缩略图 */
export function knowledgeCover(kind: 'law' | 'policy' | 'template' | 'case', label: string): string {
  const palette: Record<string, [string, string]> = {
    law: ['#6c4cf1', '#a78bfa'],
    policy: ['#3b82f6', '#60d4f5'],
    template: ['#10b981', '#6ee7b7'],
    case: ['#f59e0b', '#fbbf24'],
  }
  const [from, to] = palette[kind]
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200" viewBox="0 0 160 200">
  <defs>
    <linearGradient id="c" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${from}"/>
      <stop offset="1" stop-color="${to}"/>
    </linearGradient>
  </defs>
  <rect width="160" height="200" rx="14" fill="url(#c)"/>
  <circle cx="128" cy="34" r="44" fill="#ffffff" opacity="0.12"/>
  <rect x="26" y="54" width="76" height="8" rx="4" fill="#ffffff" opacity="0.85"/>
  <rect x="26" y="72" width="104" height="6" rx="3" fill="#ffffff" opacity="0.45"/>
  <rect x="26" y="86" width="88" height="6" rx="3" fill="#ffffff" opacity="0.35"/>
  <rect x="26" y="100" width="98" height="6" rx="3" fill="#ffffff" opacity="0.3"/>
  <text x="26" y="166" font-family="${FONT}" font-size="15" font-weight="700" fill="#ffffff">${escapeXml(label)}</text>
</svg>`
  return svgToDataUri(svg)
}

/** 登录页品牌插画 */
export function brandIllustration(): string {
  const dots = Array.from({ length: 36 })
    .map((_, i) => {
      const x = 40 + (i % 9) * 52
      const y = 40 + Math.floor(i / 9) * 52
      return `<circle cx="${x}" cy="${y}" r="2.4" fill="#ffffff" opacity="0.16"/>`
    })
    .join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="560" viewBox="0 0 640 560">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#241d52"/>
      <stop offset="0.55" stop-color="#3a2a8f"/>
      <stop offset="1" stop-color="#6c4cf1"/>
    </linearGradient>
    <linearGradient id="card" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.98"/>
      <stop offset="1" stop-color="#f0ecff" stop-opacity="0.92"/>
    </linearGradient>
  </defs>
  <rect width="640" height="560" rx="28" fill="url(#bg)"/>
  ${dots}
  <circle cx="520" cy="88" r="120" fill="#8f78f5" opacity="0.28"/>
  <circle cx="96" cy="470" r="140" fill="#22d3ee" opacity="0.12"/>
  <g transform="translate(126, 122) rotate(-6)">
    <rect width="286" height="356" rx="18" fill="url(#card)"/>
    <rect x="34" y="40" width="150" height="12" rx="6" fill="#6c4cf1" opacity="0.85"/>
    <rect x="34" y="66" width="212" height="8" rx="4" fill="#c9c3e6"/>
    <rect x="34" y="86" width="188" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="118" width="212" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="138" width="160" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="170" width="212" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="190" width="196" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="222" width="120" height="8" rx="4" fill="#ded9f2"/>
    <rect x="34" y="262" width="212" height="42" rx="10" fill="#fdf3d8"/>
    <rect x="46" y="276" width="128" height="7" rx="3.5" fill="#e3ab3c"/>
    <rect x="46" y="290" width="86" height="7" rx="3.5" fill="#f0cd8a"/>
    <circle cx="232" cy="316" r="26" fill="#fde9e9"/>
    <path d="M232 302v18M226 314h12" stroke="#e34b4b" stroke-width="3" stroke-linecap="round"/>
  </g>
  <g transform="translate(352, 214)">
    <rect width="192" height="248" rx="20" fill="#ffffff" opacity="0.98"/>
    <circle cx="46" cy="52" r="22" fill="#f2eefe"/>
    <path d="M36 52l7 8 14-16" fill="none" stroke="#6c4cf1" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="82" y="38" width="76" height="10" rx="5" fill="#2b2450" opacity="0.85"/>
    <rect x="82" y="56" width="52" height="8" rx="4" fill="#c9c3e6"/>
    <rect x="28" y="100" width="136" height="8" rx="4" fill="#ded9f2"/>
    <rect x="28" y="120" width="112" height="8" rx="4" fill="#ded9f2"/>
    <rect x="28" y="152" width="136" height="34" rx="9" fill="#6c4cf1" opacity="0.1"/>
    <rect x="40" y="165" width="72" height="8" rx="4" fill="#6c4cf1" opacity="0.55"/>
    <rect x="28" y="204" width="60" height="8" rx="4" fill="#ded9f2"/>
    <rect x="96" y="204" width="68" height="8" rx="4" fill="#ded9f2"/>
  </g>
  <g transform="translate(430, 84)">
    <rect width="126" height="42" rx="12" fill="#ffffff" opacity="0.14" stroke="#ffffff" stroke-opacity="0.25"/>
    <circle cx="24" cy="21" r="6" fill="#6ee7b7"/>
    <text x="40" y="26" font-family="${FONT}" font-size="12" fill="#ffffff">AI 实时初审</text>
  </g>
</svg>`
  return svgToDataUri(svg)
}
