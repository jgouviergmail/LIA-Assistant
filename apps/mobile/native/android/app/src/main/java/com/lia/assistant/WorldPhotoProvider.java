package com.lia.assistant;

import androidx.core.content.FileProvider;

/** A distinct provider component preserves the existing upload/camera provider. */
public final class WorldPhotoProvider extends FileProvider {
    public WorldPhotoProvider() { super(R.xml.world_share_paths); }
}
