// Toast messages, the modal dialog and the confirm dialog.
import { $, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';
import { icon } from './icons.js';

let toastTimer;
// kind: 'success' (default), 'error' or 'info'. Errors stay longer; a click dismisses any toast.
export function toast(message, kind = 'success') {
  const element = $('#toast');
  element.className = `toast ${kind}`;
  setHtml(element, html`${icon(kind === 'error' ? 'alert' : kind === 'info' ? 'info' : 'check')}<span>${message}</span>`);
  element.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), kind === 'error' ? 6000 : 3000);
}

export function showError(error) {
  toast(error?.message || String(error), 'error');
}

export function openModal(title, body) {
  const modal = $('#modal');
  setHtml(modal, html`<div class="modalbox" role="dialog" aria-modal="true" aria-label="${title}">
    <div class="between"><h3>${title}</h3><button class="button" data-action="modal.close" aria-label="Close">×</button></div>
    ${body}</div>`);
  modal.classList.add('show');
  modal.querySelector('input:not([type=hidden]), select, textarea')?.focus();
  return modal;
}

export function closeModal() {
  $('#modal').classList.remove('show');
}

// The confirm dialog has its own layer above #modal, so asking never throws away a form that is open.
let pendingConfirm = null;

function confirmLayer() {
  let layer = $('#confirm');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'confirm';
    layer.className = 'modal confirm-layer';
    document.body.append(layer);
    layer.addEventListener('click', (event) => event.target === layer && settleConfirm(false));
  }
  return layer;
}

function settleConfirm(answer) {
  confirmLayer().classList.remove('show');
  const resolve = pendingConfirm;
  pendingConfirm = null;
  resolve?.(answer);
}

export function modalIsOpen() {
  return $('#modal').classList.contains('show');
}

export const confirmIsOpen = () => Boolean(pendingConfirm);
export const cancelConfirm = () => settleConfirm(false);

/**
 * Ask before doing something that is hard to undo. Resolves true only if the person presses the confirm button.
 * message says exactly what will happen; danger=true colours the button red.
 */
export function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  settleConfirm(false);
  const layer = confirmLayer();
  setHtml(layer, html`<div class="modalbox confirm-box" role="alertdialog" aria-modal="true" aria-label="${title}">
    <h3>${title}</h3><p class="confirm-message">${message}</p>
    <div class="row" style="justify-content:flex-end"><button type="button" class="button" data-action="confirm.no">Cancel</button>
      <button type="button" class="button ${danger ? 'danger' : 'primary'}" data-action="confirm.yes" data-confirm="yes">${confirmLabel}</button></div></div>`);
  layer.classList.add('show');
  $('[data-confirm="yes"]', layer).focus();
  return new Promise((resolve) => {
    pendingConfirm = resolve;
  });
}

// Field spec: { name, label, value, type: text|number|date|password|select|textarea|tel, options:[[value,label]], required, min, step, full }
export function field(spec) {
  const { name, label, value = '', type = 'text', options = [], required, min, step, full, placeholder } = spec;
  const attrs = html`name="${name}" ${required ? html`required` : ''} ${placeholder ? html`placeholder="${placeholder}"` : ''}`;
  let control;
  if (type === 'select') {
    control = html`<select class="select" ${attrs}>${options.map(([optionValue, optionLabel]) =>
      html`<option value="${optionValue}" ${String(optionValue) === String(value) ? html`selected` : ''}>${optionLabel}</option>`)}</select>`;
  } else if (type === 'textarea') {
    control = html`<textarea class="textarea" ${attrs}>${value}</textarea>`;
  } else {
    const numberAttrs = type === 'number' ? html`min="${min ?? 0}" step="${step ?? '0.01'}"` : '';
    control = html`<input class="input" type="${type}" value="${value}" ${numberAttrs} ${attrs}>`;
  }
  return html`<label class="${full ? 'full' : ''}">${label}${control}</label>`;
}

export function formModal(title, fields, submitAction, { submitLabel = 'Save', note = '', hidden = {} } = {}) {
  return openModal(title, html`<form data-submit="${submitAction}">
    ${Object.entries(hidden).map(([name, value]) => html`<input type="hidden" name="${name}" value="${value}">`)}
    ${note ? html`<p class="small muted">${note}</p>` : ''}
    <div class="formgrid">${fields.map(field)}</div><br>
    <div class="row" style="justify-content:flex-end"><button type="button" class="button" data-action="modal.close">Cancel</button>
    <button class="button primary">${submitLabel}</button></div></form>`);
}

registerActions({
  'modal.close': closeModal,
  'confirm.yes': () => settleConfirm(true),
  'confirm.no': () => settleConfirm(false),
});

$('#toast')?.addEventListener('click', () => $('#toast').classList.remove('show'));

// Clicking the dimmed backdrop (outside the dialog box) closes the modal.
document.addEventListener('click', (event) => {
  if (event.target.id === 'modal') closeModal();
});
