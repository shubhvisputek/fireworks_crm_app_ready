// Event delegation. Markup declares behaviour with data attributes instead of inline handlers:
//   <button data-action="sales.edit" data-id="4">     -> click
//   <input data-change="cart.qty" data-index="0">       -> change
//   <input data-input="products.search">                 -> input
//   <form data-submit="settings.save">                   -> submit (default prevented)
// Handlers receive (element, event) and may be async; errors are shown as toasts.

const handlers = new Map();
let reportError = (error) => console.error(error);

export function registerActions(map) {
  for (const [name, handler] of Object.entries(map)) handlers.set(name, handler);
}

export function setErrorReporter(reporter) {
  reportError = reporter;
}

async function run(name, element, event) {
  const handler = handlers.get(name);
  if (!handler) return;
  try {
    await handler(element, event);
  } catch (error) {
    reportError(error);
  }
}

export function installActionListeners(root = document) {
  root.addEventListener('click', (event) => {
    const element = event.target.closest('[data-action]');
    if (!element || element.disabled) return;
    if (element.tagName === 'A') event.preventDefault();
    run(element.dataset.action, element, event);
  });
  for (const type of ['change', 'input', 'keydown']) {
    root.addEventListener(type, (event) => {
      const element = event.target.closest(`[data-${type}]`);
      if (element) run(element.dataset[type], element, event);
    });
  }
  root.addEventListener('submit', (event) => {
    const form = event.target.closest('form[data-submit]');
    if (!form) return;
    event.preventDefault();
    run(form.dataset.submit, form, event);
  });
}

export const formValues = (form) => Object.fromEntries(new FormData(form));
