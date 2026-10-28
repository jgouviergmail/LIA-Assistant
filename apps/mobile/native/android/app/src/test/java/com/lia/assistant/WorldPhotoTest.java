package com.lia.assistant;
import static org.junit.Assert.*;
import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import java.io.File;
import java.nio.file.Files;

public class WorldPhotoTest {
    @Rule public TemporaryFolder temporary = new TemporaryFolder();
    private byte[] header(int width, int height) {
        return new byte[]{(byte)255,(byte)216,(byte)255,(byte)192,0,8,8,
            (byte)(height >> 8),(byte)height,(byte)(width >> 8),(byte)width,1,(byte)255,(byte)217};
    }
    @Test public void boundsEnvelopeBeforeAllocation() {
        WorldPhotoInput.validateEnvelope("/9j/2Q==","image/jpeg","lia-world-photo.jpg");
        for (String encoded : new String[]{"", "=///", "////\n", "A".repeat(2796208)})
            assertThrows(IllegalArgumentException.class, () -> WorldPhotoInput.validateEnvelope(encoded,"image/jpeg","lia-world-photo.jpg"));
        assertThrows(IllegalArgumentException.class, () -> WorldPhotoInput.validateEnvelope("AAAA","image/png","lia-world-photo.jpg"));
        assertThrows(IllegalArgumentException.class, () -> WorldPhotoInput.validateEnvelope("AAAA","image/jpeg","../private.jpg"));
    }
    @Test public void boundsJpegHeadersBeforeRasterAllocation() {
        WorldPhotoInput.validateBytes(header(1600,900));
        WorldPhotoInput.validateBytes(header(1280,1600));
        for (byte[] input : new byte[][]{new byte[0],new byte[WorldPhotoInput.MAX_BYTES+1],header(1601,900),header(0,10),header(10,65535)})
            assertThrows(IllegalArgumentException.class, () -> WorldPhotoInput.validateBytes(input));
        byte[] malformed=header(800,600); malformed[4]=(byte)255; malformed[5]=(byte)255;
        assertThrows(IllegalArgumentException.class, () -> WorldPhotoInput.validateBytes(malformed));
    }
    @Test public void cacheBoundsAndExpiryPreserveUnrelatedFiles() throws Exception {
        File cache=temporary.newFolder();
        File unrelated=new File(cache,"private-data"); Files.write(unrelated.toPath(),new byte[]{7});
        long now=System.currentTimeMillis(); File first=null;
        for(int i=0;i<8;i++) { File file=WorldPhotoCache.store(cache,new byte[]{1,2,3},now); if(first==null) first=file; assertEquals("lia-world-photo.jpg",file.getName()); }
        assertThrows(IllegalStateException.class, () -> WorldPhotoCache.store(cache,new byte[]{1},now));
        File latest=WorldPhotoCache.store(cache,new byte[]{4},now+WorldPhotoCache.TTL_MS+1);
        assertFalse(first.exists()); assertTrue(latest.isFile()); assertArrayEquals(new byte[]{7},Files.readAllBytes(unrelated.toPath()));
        WorldPhotoCache.remove(latest); assertFalse(latest.getParentFile().exists());
    }
}
