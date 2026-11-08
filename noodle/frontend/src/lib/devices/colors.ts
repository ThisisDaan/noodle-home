import { COLORS, type CardColor } from './cardDesign.ts';
import { isHex } from './cardText.ts';

/** A colour in a template is a named one (classes, so the theme can change it) or any hex colour (an inline style). */
const preset = (c?: string) => (c && Object.hasOwn(COLORS, c) ? COLORS[c as CardColor] : undefined);
export const textClass = (c?: string) => preset(c)?.text ?? '';
export const textStyle = (c?: string) => (isHex(c) ? `color:${c};` : '');
export const fillClassOf = (c?: string) => preset(c)?.fill ?? '';
export const fillStyle = (c?: string) => (isHex(c) ? `background:${c};` : '');
export const tintClass = (c?: string) => preset(c)?.tint ?? '';
export const tintStyle = (c?: string) => (isHex(c) ? `background:${c};` : '');
