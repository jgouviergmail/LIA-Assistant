import type { HomeEdit, HomeView } from './home-protocol';
import type { HomeSkin } from './home-projection';

/** Preview only the owner's selected or application-derived colours. */
export function previewHome(view: HomeView, edit: HomeEdit): HomeSkin {
  return {
    palette: edit.palette === 'auto' ? view.decoration.automatic_palette : edit.palette,
  };
}
