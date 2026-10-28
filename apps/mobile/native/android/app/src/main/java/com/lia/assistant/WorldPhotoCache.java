package com.lia.assistant;

import java.io.File;
import java.io.FileOutputStream;
import java.util.UUID;

/** Bounded private cache, independent of Android UI and testable on the JVM. */
final class WorldPhotoCache {
    static final long TTL_MS = 15 * 60 * 1000;
    private WorldPhotoCache() {}
    static File store(File cache, byte[] bytes, long now) throws Exception {
        File root = new File(cache, "world-share");
        if (!root.isDirectory() && !root.mkdirs()) throw new IllegalStateException();
        File[] entries = root.listFiles();
        if (entries == null) throw new IllegalStateException();
        int count = 0;
        for (File entry : entries) {
            if (entry.isDirectory() && now - entry.lastModified() >= TTL_MS)
                remove(new File(entry, "lia-world-photo.jpg"));
            if (entry.exists()) count++;
        }
        if (count >= 8) throw new IllegalStateException("world_photo_cache_full");
        File directory = new File(root, UUID.randomUUID().toString());
        if (!directory.mkdir()) throw new IllegalStateException();
        File image = new File(directory, "lia-world-photo.jpg");
        try (FileOutputStream output = new FileOutputStream(image)) { output.write(bytes); }
        catch (Exception error) { remove(image); throw error; }
        directory.setLastModified(now);
        return image;
    }
    static void remove(File image) {
        image.delete();
        File directory = image.getParentFile();
        if (directory != null) directory.delete();
    }
}
