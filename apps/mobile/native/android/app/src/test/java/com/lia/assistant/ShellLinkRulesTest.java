package com.lia.assistant;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** Which way an address goes, and what a file is called. */
public class ShellLinkRulesTest {

    private static final String SERVER = "lia.example.org";

    @Test
    public void onlyAWebOrMailAddressLeavesForAnotherApplication() {
        assertTrue(ShellLinkRules.mayLeave("https"));
        assertTrue(ShellLinkRules.mayLeave("HTTP"));
        assertTrue(ShellLinkRules.mayLeave("mailto"));
        assertFalse(ShellLinkRules.mayLeave("intent"));
        assertFalse(ShellLinkRules.mayLeave("file"));
        assertFalse(ShellLinkRules.mayLeave("javascript"));
        assertFalse(ShellLinkRules.mayLeave("about"));
        assertFalse(ShellLinkRules.mayLeave("blob"));
        assertFalse(ShellLinkRules.mayLeave(null));
    }

    @Test
    public void theServerAndItsApiAreOneSite() {
        assertTrue(ShellLinkRules.isSameSite(SERVER, SERVER));
        assertTrue(ShellLinkRules.isSameSite(SERVER, "LIA.example.org"));
        assertTrue(ShellLinkRules.isSameSite(SERVER, "lia-back.example.org"));
        assertTrue(ShellLinkRules.isSameSite("example.org", "api.example.org"));
        assertTrue(ShellLinkRules.isSameSite("api.example.org", "example.org"));
    }

    @Test
    public void aTopLevelDomainIsNoSite() {
        assertFalse(ShellLinkRules.isSameSite("example.org", "other.org"));
        assertFalse(ShellLinkRules.isSameSite("lia.example.org", "lia.other.org"));
        assertFalse(ShellLinkRules.isSameSite("localhost", "otherhost"));
    }

    @Test
    public void nothingIsTheSiteOfAServerNobodyNamed() {
        assertFalse(ShellLinkRules.isSameSite(null, SERVER));
        assertFalse(ShellLinkRules.isSameSite(SERVER, null));
    }

    @Test
    public void aSuffixThatIsNotADomainIsNoSite() {
        assertFalse(ShellLinkRules.isSameSite("example.org", "notexample.org"));
    }

    @Test
    public void aFileOfTheApiStaysInTheWebViewThatHoldsTheSession() {
        assertTrue(ShellLinkRules.isServerApi(SERVER, "lia-back.example.org", "/api/v1/files/x"));
        assertTrue(ShellLinkRules.isServerApi(SERVER, SERVER, "/api/v1/files/x"));
    }

    @Test
    public void anythingElseOfTheSiteKeepsItsWay() {
        assertFalse(ShellLinkRules.isServerApi(SERVER, "blog.example.org", "/post"));
        assertFalse(ShellLinkRules.isServerApi(SERVER, "other.org", "/api/v1/files/x"));
        assertFalse(ShellLinkRules.isServerApi(SERVER, SERVER, null));
    }

    @Test
    public void aNameInUtf8IsReadWhole() {
        assertEquals(
            "compte rendu été.pdf",
            ShellLinkRules.encodedFileName(
                "attachment; filename=\"compte rendu ete.pdf\"; "
                    + "filename*=UTF-8''compte%20rendu%20%C3%A9t%C3%A9.pdf"
            )
        );
    }

    @Test
    public void aNameKeepsNoPath() {
        assertEquals(
            "passwd",
            ShellLinkRules.encodedFileName("attachment; filename*=UTF-8''..%2F..%2Fetc%2Fpasswd")
        );
        assertEquals(
            "evil.txt",
            ShellLinkRules.encodedFileName("attachment; filename*=UTF-8''..%5Cevil.txt")
        );
    }

    @Test
    public void aHeaderWithNoEncodedNameLeavesTheDecisionToThePlatform() {
        assertNull(ShellLinkRules.encodedFileName("attachment; filename=\"plain.txt\""));
        assertNull(ShellLinkRules.encodedFileName(null));
    }

    @Test
    public void aNameThatCannotBeReadIsNoName() {
        assertNull(ShellLinkRules.encodedFileName("attachment; filename*=UTF-8''%ZZ"));
        assertNull(ShellLinkRules.encodedFileName("attachment; filename*=UTF-8''..%2F"));
    }
}
