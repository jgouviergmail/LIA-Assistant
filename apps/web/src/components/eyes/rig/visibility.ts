/** One owner for page/viewport suspension; invisible previews consume no frames. */
export function observeRigVisibility(element: HTMLElement, changed: (visible: boolean) => void) {
  let intersecting = true;
  const notify = () => changed(intersecting && !document.hidden);
  const observer =
    typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver(entries => {
          intersecting = entries.some(entry => entry.isIntersecting);
          notify();
        });
  observer?.observe(element);
  document.addEventListener('visibilitychange', notify);
  return () => {
    observer?.disconnect();
    document.removeEventListener('visibilitychange', notify);
  };
}
