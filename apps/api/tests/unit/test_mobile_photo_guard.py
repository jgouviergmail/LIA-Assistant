"""Authored native image boundary stays narrow through shell regeneration."""

import xml.etree.ElementTree as ET

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
ANDROID = ROOT / "apps/mobile/native/android/app/src/main"
IOS = ROOT / "apps/mobile/native/ios/App/App"


def test_world_photo_provider_exposes_only_its_private_cache() -> None:
    ns = "{http://schemas.android.com/apk/res/android}"
    providers = ET.parse(ANDROID / "AndroidManifest.xml").findall(".//provider")
    photo = [p for p in providers if p.get(ns + "authorities") == "${applicationId}.worldshare"]
    assert len(photo) == 1
    assert photo[0].get(ns + "name") == ".WorldPhotoProvider"
    assert photo[0].get(ns + "exported") == "false"
    assert photo[0].get(ns + "grantUriPermissions") == "true"
    paths = ET.parse(ANDROID / "res/xml/world_share_paths.xml").getroot()
    assert [(p.tag, p.get("path")) for p in paths] == [("cache-path", "world-share/")]
    assert any(p.get(ns + "authorities") == "${applicationId}.fileprovider" for p in providers)


def test_photo_helper_is_compiled_by_generated_xcode_project() -> None:
    prepare = (ROOT / "apps/mobile/scripts/prepare.mjs").read_text(encoding="utf-8")
    assert "'WorldImageShare.swift'" in prepare
    assert (IOS / "WorldImageShare.swift").is_file()


def test_the_share_sheet_may_save_the_photo_without_terminating_the_app() -> None:
    # The activity sheet offers "Save Image" for an image file; iOS kills an
    # app that writes to the photo library without a usage description.
    plist = (IOS / "Info.plist").read_text(encoding="utf-8")
    assert "<key>NSPhotoLibraryAddUsageDescription</key>" in plist
