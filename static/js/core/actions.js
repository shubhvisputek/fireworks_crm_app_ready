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

// While an action is still working, its button is disabled and shows a spinner, so a slow
// network can't cause a double click to save twice (for example, two copies of one bill).
function busyButton(element, event) {
  if (event.type === 'submit') return event.submitter || element.querySelector('button:not([type=button])');
  return element.tagName === 'BUTTON' ? element : null;
}

async function run(name, element, event) {
  const handler = handlers.get(name);
  if (!handler) return;
  let button = null;
  try {
    const result = handler(element, event);
    if (result && typeof result.then === 'function') {
      button = busyButton(element, event);
      if (button) {
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
      }
      await result;
    }
  } catch (error) {
    reportError(error);
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
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
