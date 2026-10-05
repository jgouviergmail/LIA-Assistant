/** Activate the browser's RTC audio decoder without adding an audible sink. */
export function activateRtcAudio(stream: MediaStream): () => void {
  // Chromium otherwise delivers silence to a Web Audio consumer of a remote
  // RTC track. Muting is reliable on mobile too; HTML volume is not the gate.
  const element = document.createElement('audio');
  element.muted = element.defaultMuted = true;
  element.hidden = true;
  element.setAttribute('aria-hidden', 'true');
  element.srcObject = stream;
  document.body.appendChild(element);
  void element.play()?.catch(() => {});
  let released = false;
  return () => {
    if (released) return;
    released = true;
    element.pause();
    element.srcObject = null;
    element.remove();
  };
}
