/* Hermetic SDK boundary: real React details, no Places or Directions service. */
(() => {
  const callback = new URL(document.currentScript.src).searchParams.get('callback').split('.')[1];
  const witness = {
    maps: 0,
    markers: [],
    pins: [],
    bounds: [],
    options: [],
    sizes: [],
    polylines: [],
    infoWindows: 0,
    infoWindowOptions: [],
    popupOpens: [],
    libraryCalls: [],
    placesCalls: 0,
  };
  window.__positionWitness = witness;
  const markers = [];
  window.__clickPositionMarker = index => markers[index].dispatchEvent(new Event('gmp-click'));
  class Map {
    constructor(element, options) {
      this.id = ++witness.maps;
      this.element = element;
      witness.options.push(options);
      const box = element.getBoundingClientRect();
      witness.sizes.push({
        width: box.width,
        height: box.height,
        stageHidden: element.closest('.lia-place-position__stage').hidden,
      });
      if (box.width < 50 || box.height < 100) throw Error('collapsed');
      element.innerHTML =
        '<div style="height:100%;background:#d8e9dd;color:#111;display:grid;place-items:center">LOCAL_POSITION_MAP</div>';
    }
    fitBounds(bounds) {
      witness.bounds.push(bounds);
    }
    setOptions(options) {
      witness.options.push(options);
    }
  }
  class Marker extends HTMLElement {
    constructor(options) {
      super();
      this.index = markers.length;
      this.dataset.positionSdkMarker = String(this.index);
      this.setAttribute('role', 'button');
      this.setAttribute('aria-label', options.title);
      this.tabIndex = 0;
      this.style.cssText = `position:absolute;left:calc(${15 + this.index * 25}% - 22px);top:55%;display:grid;place-items:center;width:44px;height:44px;cursor:pointer`;
      this.map = options.map;
      this.zIndex = options.zIndex;
      this.addEventListener('click', () => this.dispatchEvent(new Event('gmp-click')));
      this.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        this.dispatchEvent(new Event('gmp-click'));
      });
      markers.push(this);
      witness.markers.push({ ...options, map: options.map.id });
    }
    get map() {
      return this._map;
    }
    set map(map) {
      this._map = map;
      if (map) map.element.append(this);
      else this.remove();
    }
    get zIndex() {
      return this._zIndex;
    }
    set zIndex(value) {
      this._zIndex = value;
      this.style.zIndex = String(value);
    }
  }
  class PinElement extends HTMLElement {
    constructor(options) {
      super();
      this.record = { ...options };
      witness.pins.push(this.record);
      this.style.cssText =
        'display:grid;place-items:center;width:32px;height:36px;border:2px solid;border-radius:50% 50% 50% 0;transform:rotate(-45deg);font:600 14px sans-serif';
      this.glyph = document.createElement('span');
      this.glyph.dataset.positionSdkGlyph = '';
      this.glyph.style.transform = 'rotate(45deg)';
      this.append(this.glyph);
      this.glyphText = options.glyphText;
      this.background = options.background ?? '#c5221f';
      this.borderColor = options.borderColor ?? '#8c1b17';
      this.glyphColor = options.glyphColor ?? '#fff';
    }
    get glyphText() {
      return this.record.glyphText;
    }
    set glyphText(value) {
      this.record.glyphText = value;
      this.glyph.textContent = value;
    }
    get background() {
      return this.record.background;
    }
    set background(value) {
      this.record.background = value;
      this.style.backgroundColor = value;
    }
    get borderColor() {
      return this.record.borderColor;
    }
    set borderColor(value) {
      this.record.borderColor = value;
      this.style.borderColor = value;
    }
    get glyphColor() {
      return this.record.glyphColor;
    }
    set glyphColor(value) {
      this.record.glyphColor = value;
      this.style.color = value;
    }
  }
  customElements.define('position-sdk-marker', Marker);
  customElements.define('position-sdk-pin', PinElement);
  class Polyline {
    constructor(options) {
      this.record = { map: options.map.id, path: options.path, options: [] };
      witness.polylines.push(this.record);
    }
    setMap(map) {
      this.record.map = map?.id ?? null;
    }
    setOptions(options) {
      this.record.options.push(options);
      if (options.path) this.record.path = options.path;
    }
    addListener() {
      return { remove() {} };
    }
  }
  class InfoWindow {
    constructor(options) {
      witness.infoWindows++;
      witness.infoWindowOptions.push(options);
      this.shell = document.createElement('div');
      this.shell.className = 'gm-style-iw-c';
      // The native shell owns the header/close control; only its content body
      // scrolls. The portal subtree keeps its natural height, as with Google.
      this.shell.style.cssText = `position:absolute;top:8px;left:8px;display:flex;flex-direction:column;max-width:min(${options.maxWidth}px,calc(100% - 16px));max-height:calc(100% - 16px);box-sizing:border-box;overflow:hidden;background:var(--color-background);color:var(--color-foreground);border-radius:12px;box-shadow:0 2px 8px #0003`;
      const header = document.createElement('div');
      header.className = 'gm-style-iw-chr';
      header.style.cssText =
        'display:flex;align-items:flex-start;justify-content:space-between;gap:8px;flex:none;padding:8px 8px 0 12px';
      this.header = document.createElement('div');
      this.header.className = 'gm-style-iw-ch';
      this.header.style.cssText = 'min-width:0;flex:1';
      this.closeListeners = new Set();
      const close = document.createElement('button');
      close.type = 'button';
      close.setAttribute('aria-label', 'Fermer');
      close.textContent = '×';
      close.style.cssText = 'width:44px;height:44px;font-size:24px;flex:none';
      close.addEventListener('click', () => {
        this.close();
      });
      this.shell.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        this.close();
      });
      header.append(this.header, close);
      this.body = document.createElement('div');
      this.body.className = 'gm-style-iw-d';
      this.body.style.cssText =
        'min-height:0;overflow:auto;padding:0 12px 12px;box-sizing:border-box';
      this.shell.append(header, this.body);
    }
    setContent(content) {
      if (this.body.firstChild === content) return;
      this.body.replaceChildren(...(content ? [content] : []));
      this.body.scrollTop = 0;
    }
    setOptions(options) {
      if (options.ariaLabel) {
        this.shell.setAttribute('role', 'dialog');
        this.shell.setAttribute('aria-label', options.ariaLabel);
      }
      if (Object.hasOwn(options, 'headerContent'))
        this.header.replaceChildren(...(options.headerContent ? [options.headerContent] : []));
    }
    addListener(event, listener) {
      if (event !== 'close') throw Error('Unexpected InfoWindow listener');
      this.closeListeners.add(listener);
      return { remove: () => this.closeListeners.delete(listener) };
    }
    open(options) {
      witness.popupOpens.push({
        map: options.map.id,
        marker: options.anchor.index,
        shouldFocus: options.shouldFocus,
      });
      options.map.element.append(this.shell);
    }
    close() {
      const open = this.shell.isConnected;
      this.shell.remove();
      if (open) this.closeListeners.forEach(listener => listener());
    }
  }
  class Bounds {
    constructor(value) {
      Object.assign(this, value);
    }
    extend() {}
  }
  const rejectPlaces = class {
    constructor() {
      witness.placesCalls++;
      throw Error('Places must not be called');
    }
  };
  window.google = {
    maps: {
      Map,
      Marker,
      Polyline,
      InfoWindow,
      LatLngBounds: Bounds,
      places: { Place: rejectPlaces, PlacesService: rejectPlaces },
      MapTypeControlStyle: { DROPDOWN_MENU: 1 },
      event: { clearInstanceListeners() {} },
      importLibrary: async library => {
        witness.libraryCalls.push(library);
        if (library !== 'marker') throw Error('Unexpected SDK library');
        return { AdvancedMarkerElement: Marker, PinElement };
      },
    },
  };
  window.liaRouteMapsCallbacks[callback]();
})();
