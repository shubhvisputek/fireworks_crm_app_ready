// Toast messages and the modal dialog.
import { $, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';

let toastTimer;
export function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 3000);
}

export function showError(error) {
  toast(error?.message || String(error));
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

export function modalIsOpen() {
  return $('#modal').classList.contains('show');
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

registerActions({ 'modal.close': closeModal });

// Clicking the dimmed backdrop (outside the dialog box) closes the modal.
document.addEventListener('click', (event) => {
  if (event.target.id === 'modal') closeModal();
});
