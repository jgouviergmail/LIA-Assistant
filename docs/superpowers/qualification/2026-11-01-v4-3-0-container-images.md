# v4.3.0 container-image qualification — 1 November 2026

**Status: application qualification passed; upstream image findings remain open.** The local API image scan is red and is not represented as clean. Runtime, migration, application and installer checks pass. The owner directed continuation where there is no technical or functional blocker. Mandatory CI, Security and disposable-installer gates still determine publication readiness. The web image has no high or critical finding in the same database snapshot.

## Scope and method

These are local native amd64 images rebuilt without cache from the release working tree. They do not replace the immutable candidate workflow or the four disposable installer legs on amd64 and arm64. The source was uncommitted at measurement time.

| Image | Local configuration digest |
| --- | --- |
| API | `sha256:93ece890b3ec6e7dcc853ac6027da0462454335b906697821105f686644bd688` |
| Web | `sha256:ce8e68c4e6293a54851134019d752dea2db3a44f29f091f35050a607a1a322b6` |

Trivy 0.74.0 used a freshly downloaded vulnerability database with the HIGH/CRITICAL blocking threshold. The machine-readable local evidence is retained with the release qualification artifacts. Scanner severity is a prioritization input, not a completed exploitability assessment. In particular, Debian calls the libxml2 issue below minor while the scanner classifies it as critical.

## Corrections applied and verified

- The application uses the fixed WebSocket library and compatible SDK baselines. Strict local TLS and Uvicorn SansIO fixtures pass inside the rebuilt Linux image, and `pip check` reports no broken dependency.
- API, development and skill-sandbox images now pin matching pip 26.2.2 and npm 12.2.1. The single-owner build-input guard passed after first detecting the missing pins.
- The updated API image no longer reports the compromised certifi root in pip, or the two npm brace-expansion advisories. The application had already carried a corrected certifi; pip owns a separate vendored store.
- The pip bootstrap wheel is checked against its published SHA-256 in all three recipes. The existing guard caught the initial omission; all 26 related checks and the final complete parallel unit run pass. Native API and sandbox rebuilds and runtime probes pass after that correction.
- The rebuilt sandbox passes its 25 library, 18 command and two absence probes.
- The production web image passes 66 rendered public-page probes across six languages.

## Remaining API findings

The scan reports 273 Debian package findings representing **69 distinct advisories**, plus **nine findings in embedded tools**. None of the Debian findings has a corrected trixie package version in this scanner snapshot. A fresh update of the signed APT indexes confirms that the installed Chromium, FFmpeg and libxml2 versions are the current candidates; Docker Compose also equals the current candidate. This does not make these findings safe.

Chromium 156.0.8078.73 remains affected by [CVE-2026-119260](https://security-tracker.debian.org/tracker/CVE-2026-119260): a hostile page can execute code inside the browser sandbox before 156.0.8078.79. The browser processes external content, so the advisory cannot be dismissed as an unused development dependency. [Debian also still marks the installed libxml2 as vulnerable](https://security-tracker.debian.org/tracker/CVE-2026-6653). Mixing unstable distribution libraries or locally rewriting vendor packages has not been accepted as a release repair.

### Embedded tools

These entries identify what still requires an upstream update or a separate, evidenced reachability verdict; they are not new exceptions.

The image probe establishes that pip's MessagePack uses its pure-Python
`fallback.Unpacker` and contains no `_cmsgpack` extension. The publisher's
[memory-leak advisory](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-j586-36cw-2gc2)
concerns the C extension; the [other correction changes its C unpacker](https://github.com/msgpack/msgpack-python/commit/2c56ddb5d0025ed481d962c0f5d62d19dec7476d).
The same probe establishes that neither an installed setuptools package nor
the vulnerable `setuptools.package_index` module exists in the image;
[the setuptools advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf)
requires `PackageIndex.download`. These three inventory findings do not identify
their affected code in this measured image. Application MessagePack is the
patched 1.2.3. No scan filter or blanket package exception was introduced.

| Owner | Package | Installed | Fixed library release | Advisory |
| --- | --- | --- | --- | --- |
| npm | undici | 6.29.0 | 6.29.1, 7.30.1, 8.12.2 | [CVE-2026-109383](https://avd.aquasec.com/nvd/cve-2026-109383) |
| npm | undici | 6.29.0 | 6.29.1, 7.30.1, 8.12.2 | [CVE-2026-109869](https://avd.aquasec.com/nvd/cve-2026-109869) |
| npm | undici | 6.29.0 | 6.29.1, 7.30.1, 8.12.2 | [CVE-2026-87018](https://avd.aquasec.com/nvd/cve-2026-87018) |
| pip vendored inventory | msgpack | 1.1.2 | 1.2.3 | [CVE-2026-114613](https://avd.aquasec.com/nvd/cve-2026-114613) |
| pip vendored inventory | msgpack | 1.1.2 | 1.2.1 | [GHSA-6v7p-g79w-8964](https://github.com/advisories/GHSA-6v7p-g79w-8964) |
| pip vendored inventory | setuptools | 70.3.0 | 78.1.1 | [CVE-2025-47273](https://avd.aquasec.com/nvd/cve-2025-47273) |
| pip vendored inventory | urllib3 | 2.7.0 | 2.8.0 | [CVE-2026-97687](https://avd.aquasec.com/nvd/cve-2026-97687) |
| pip vendored inventory | urllib3 | 2.7.0 | 2.8.0 | [CVE-2026-97689](https://avd.aquasec.com/nvd/cve-2026-97689) |
| Docker Compose | golang.org/x/net | v0.58.0 | 0.60.0 | [CVE-2026-78669](https://avd.aquasec.com/nvd/cve-2026-78669) |

### Debian advisory inventory

Several binary packages can carry one source-package issue; the table therefore groups the report by advisory rather than summing duplicate package rows.

| Advisory | Binary packages reported |
| --- | --- |
| [CVE-2022-4055](https://security-tracker.debian.org/tracker/CVE-2022-4055) | xdg-utils |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | libncursesw6, libtinfo6, ncurses-base, ncurses-bin |
| [CVE-2026-119260](https://security-tracker.debian.org/tracker/CVE-2026-119260) | chromium, chromium-common |
| [CVE-2026-119261](https://security-tracker.debian.org/tracker/CVE-2026-119261) | chromium, chromium-common |
| [CVE-2026-119262](https://security-tracker.debian.org/tracker/CVE-2026-119262) | chromium, chromium-common |
| [CVE-2026-119263](https://security-tracker.debian.org/tracker/CVE-2026-119263) | chromium, chromium-common |
| [CVE-2026-119264](https://security-tracker.debian.org/tracker/CVE-2026-119264) | chromium, chromium-common |
| [CVE-2026-119265](https://security-tracker.debian.org/tracker/CVE-2026-119265) | chromium, chromium-common |
| [CVE-2026-119266](https://security-tracker.debian.org/tracker/CVE-2026-119266) | chromium, chromium-common |
| [CVE-2026-119267](https://security-tracker.debian.org/tracker/CVE-2026-119267) | chromium, chromium-common |
| [CVE-2026-119268](https://security-tracker.debian.org/tracker/CVE-2026-119268) | chromium, chromium-common |
| [CVE-2026-119269](https://security-tracker.debian.org/tracker/CVE-2026-119269) | chromium, chromium-common |
| [CVE-2026-119270](https://security-tracker.debian.org/tracker/CVE-2026-119270) | chromium, chromium-common |
| [CVE-2026-119271](https://security-tracker.debian.org/tracker/CVE-2026-119271) | chromium, chromium-common |
| [CVE-2026-12064](https://security-tracker.debian.org/tracker/CVE-2026-12064) | curl, libcurl4t64 |
| [CVE-2026-16554](https://security-tracker.debian.org/tracker/CVE-2026-16554) | libcjson1 |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | libnss-systemd, libpam-systemd, libsystemd-shared, libsystemd0, libudev1, systemd, systemd-cryptsetup, systemd-sysv, systemd-timesyncd |
| [CVE-2026-24882](https://security-tracker.debian.org/tracker/CVE-2026-24882) | dirmngr, gnupg, gnupg-l10n, gpg, gpg-agent, gpgconf, gpgsm |
| [CVE-2026-29036](https://security-tracker.debian.org/tracker/CVE-2026-29036) | libcjson1 |
| [CVE-2026-34980](https://security-tracker.debian.org/tracker/CVE-2026-34980) | libcups2t64 |
| [CVE-2026-36849](https://security-tracker.debian.org/tracker/CVE-2026-36849) | libtiff6 |
| [CVE-2026-37555](https://security-tracker.debian.org/tracker/CVE-2026-37555) | libsndfile1 |
| [CVE-2026-52490](https://security-tracker.debian.org/tracker/CVE-2026-52490) | libtiff6 |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | libacl1 |
| [CVE-2026-55453](https://security-tracker.debian.org/tracker/CVE-2026-55453) | libcups2t64 |
| [CVE-2026-58049](https://security-tracker.debian.org/tracker/CVE-2026-58049) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-64830](https://security-tracker.debian.org/tracker/CVE-2026-64830) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-64832](https://security-tracker.debian.org/tracker/CVE-2026-64832) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-64833](https://security-tracker.debian.org/tracker/CVE-2026-64833) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-64834](https://security-tracker.debian.org/tracker/CVE-2026-64834) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-64835](https://security-tracker.debian.org/tracker/CVE-2026-64835) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-66036](https://security-tracker.debian.org/tracker/CVE-2026-66036) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-66039](https://security-tracker.debian.org/tracker/CVE-2026-66039) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-66040](https://security-tracker.debian.org/tracker/CVE-2026-66040) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-66041](https://security-tracker.debian.org/tracker/CVE-2026-66041) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653) | libxml2 |
| [CVE-2026-67215](https://security-tracker.debian.org/tracker/CVE-2026-67215) | libcjson1 |
| [CVE-2026-67216](https://security-tracker.debian.org/tracker/CVE-2026-67216) | libcjson1 |
| [CVE-2026-70628](https://security-tracker.debian.org/tracker/CVE-2026-70628) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-70632](https://security-tracker.debian.org/tracker/CVE-2026-70632) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-74860](https://security-tracker.debian.org/tracker/CVE-2026-74860) | libxml2 |
| [CVE-2026-75142](https://security-tracker.debian.org/tracker/CVE-2026-75142) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-75143](https://security-tracker.debian.org/tracker/CVE-2026-75143) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-75144](https://security-tracker.debian.org/tracker/CVE-2026-75144) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-75146](https://security-tracker.debian.org/tracker/CVE-2026-75146) | ffmpeg, libavcodec61, libavdevice61, libavfilter10, libavformat61, libavutil59, libpostproc58, libswresample5, libswscale8 |
| [CVE-2026-76024](https://security-tracker.debian.org/tracker/CVE-2026-76024) | chromium, chromium-common |
| [CVE-2026-76025](https://security-tracker.debian.org/tracker/CVE-2026-76025) | chromium, chromium-common |
| [CVE-2026-76026](https://security-tracker.debian.org/tracker/CVE-2026-76026) | chromium, chromium-common |
| [CVE-2026-76027](https://security-tracker.debian.org/tracker/CVE-2026-76027) | chromium, chromium-common |
| [CVE-2026-76028](https://security-tracker.debian.org/tracker/CVE-2026-76028) | chromium, chromium-common |
| [CVE-2026-76029](https://security-tracker.debian.org/tracker/CVE-2026-76029) | chromium, chromium-common |
| [CVE-2026-76030](https://security-tracker.debian.org/tracker/CVE-2026-76030) | chromium, chromium-common |
| [CVE-2026-76031](https://security-tracker.debian.org/tracker/CVE-2026-76031) | chromium, chromium-common |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409) | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux |
| [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux |
| [CVE-2026-8458](https://security-tracker.debian.org/tracker/CVE-2026-8458) | curl, libcurl4t64 |
| [CVE-2026-86138](https://security-tracker.debian.org/tracker/CVE-2026-86138) | libxml2 |
| [CVE-2026-86139](https://security-tracker.debian.org/tracker/CVE-2026-86139) | libxml2 |
| [CVE-2026-86140](https://security-tracker.debian.org/tracker/CVE-2026-86140) | libxml2 |
| [CVE-2026-86142](https://security-tracker.debian.org/tracker/CVE-2026-86142) | libxml2 |
| [CVE-2026-86143](https://security-tracker.debian.org/tracker/CVE-2026-86143) | libxml2 |
| [CVE-2026-86144](https://security-tracker.debian.org/tracker/CVE-2026-86144) | libxml2 |
| [CVE-2026-87933](https://security-tracker.debian.org/tracker/CVE-2026-87933) | libcjson1 |
| [CVE-2026-88806](https://security-tracker.debian.org/tracker/CVE-2026-88806) | libx11-6, libx11-data, libx11-xcb1 |
| [CVE-2026-88807](https://security-tracker.debian.org/tracker/CVE-2026-88807) | libxrender1 |
| [CVE-2026-94286](https://security-tracker.debian.org/tracker/CVE-2026-94286) | libxtst6 |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | libperl5.40, perl, perl-base, perl-modules-5.40 |

## Exit conditions

The owner initially chose on 1 November to wait, then directed continuation
provided there is no technical or functional blocker. The completed application,
readiness, migration and installer checks show no such blocker. The remaining
image advisories are disclosed upstream security debt, including the reachable
browser risk described above; they are not claimed fixed or absent. No browser
replacement or container-scan exception is integrated. An isolated amd64 prototype
using official Chrome for Testing 156.0.8078.80 passed the API's actual
Playwright navigation, JavaScript, click, screenshot and PDF probes. Official
amd64 and arm64 archives were inspected; arm64 execution could not be qualified
locally because the Docker host has no arm64 emulation. This experiment does
not change the release image or remove its findings.

Keep the raw findings visible and revisit them when vendor corrections arrive. Rebuild and rescan after a correction or a reviewed architectural remedy, then repeat affected runtime and installer probes. Do not label the image clean because a lockfile audit passed, invent a not-affected verdict, or disable a scan threshold. Publication requires passing repository CI and Security on the exact SHA and the hash-bound disposable installer qualification. This report separates those required gates from the additional full-image finding inventory; the release plan records the independent application results.
