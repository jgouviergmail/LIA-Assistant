package com.lia.assistant;


/** Pure bounded input validation before native image allocation or disk access. */
final class WorldPhotoInput {
    static final int MAX_BYTES = 2 * 1024 * 1024;
    private WorldPhotoInput() {}
    static void validateEnvelope(String encoded, String mime, String filename) {
        if (!"image/jpeg".equals(mime) || !"lia-world-photo.jpg".equals(filename)
            || encoded == null || encoded.length() == 0 || encoded.length() > 2796204
            || encoded.length() % 4 != 0 || !encoded.matches("[A-Za-z0-9+/]*={0,2}")) {
            throw new IllegalArgumentException("world_photo_input");
        }
    }
    static void validateBytes(byte[] bytes) {
        if (bytes.length < 12 || bytes.length > MAX_BYTES || u(bytes[0]) != 255
            || u(bytes[1]) != 216 || u(bytes[2]) != 255
            || u(bytes[bytes.length - 2]) != 255 || u(bytes[bytes.length - 1]) != 217) {
            throw new IllegalArgumentException("world_photo_jpeg");
        }
        dimensions(bytes);

    }
    private static int u(byte value) { return value & 255; }
    private static int word(byte[] bytes, int at) { return (u(bytes[at]) << 8) | u(bytes[at + 1]); }
    private static void dimensions(byte[] bytes) {
        int at = 2;
        while (at + 4 < bytes.length) {
            if (u(bytes[at++]) != 255) break;
            while (at < bytes.length && u(bytes[at]) == 255) at++;
            if (at + 3 >= bytes.length) break;
            int marker = u(bytes[at++]);
            if (marker == 218 || marker == 217 || marker == 0) break;
            int length = word(bytes, at);
            if (length < 2 || length > bytes.length - at) break;
            if (marker == 192 || marker == 193 || marker == 194) {
                if (length < 8 || u(bytes[at + 2]) != 8) break;
                int height = word(bytes, at + 3), width = word(bytes, at + 5);
                if (width < 1 || height < 1 || width > 1600 || height > 1600
                    || (long) width * height > 2560000) break;
                return;
            }
            at += length;
        }
        throw new IllegalArgumentException("world_photo_dimensions");
    }
}
