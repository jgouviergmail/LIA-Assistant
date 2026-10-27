import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

import * as xcode from '../xcode-sources.mjs';
import * as gradle from '../android-gradle.mjs';

function fixture(t) {
  const directory = mkdtempSync(join(tmpdir(), 'lia-native-build-'));
  t.after(() => {
    assert.equal(dirname(resolve(directory)), resolve(tmpdir()));
    assert.ok(directory.startsWith(join(tmpdir(), 'lia-native-build-')));
    rmSync(directory, { recursive: true, force: true });
  });
  return directory;
}

function write(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
  return path;
}

const targetId = '1234567890ABCDEF12345678';
const projectText = (id = targetId) => `/* Begin PBXNativeTarget section */
\t\t${id} /* App */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tname = App;
\t\t\tproductReference = ABCDEF1234567890ABCDEF12 /* App.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t};
/* End PBXNativeTarget section */
`.replaceAll('\\t', '\t');

function iosFixture(t, swift = 'import UIKit\n') {
  const directory = fixture(t);
  const project = write(join(directory, 'App.xcodeproj/project.pbxproj'), projectText());
  write(join(directory, 'App/Main.swift'), swift);
  return { directory, project };
}

test('shared App scheme derives the target UUID and is idempotent', t => {
  const { project } = iosFixture(t);
  const first = xcode.ensureSharedAppScheme(project);
  const content = readFileSync(first.path, 'utf8');
  assert.match(content, new RegExp(`BlueprintIdentifier="${targetId}"`));
  assert.match(content, /parallelizeBuildables="YES"/);
  assert.match(content, /buildImplicitDependencies="YES"/);
  assert.match(content, /BuildableName="App.app"/);
  assert.match(content, /LaunchAction buildConfiguration="Debug"/);
  assert.match(content, /BuildableProductRunnable runnableDebuggingMode="0"/);
  assert.match(content, /ArchiveAction buildConfiguration="Release"/);
  assert.equal(first.created, true);
  assert.equal(xcode.ensureSharedAppScheme(project).created, false);
  assert.equal(readFileSync(first.path, 'utf8'), content);
});

test('shared scheme never overwrites an unexpected existing file', t => {
  const { project } = iosFixture(t);
  const scheme = write(join(dirname(project), 'xcshareddata/xcschemes/App.xcscheme'), '<Scheme owner="user"/>');
  assert.throws(() => xcode.ensureSharedAppScheme(project), /existing|collision/i);
  assert.equal(readFileSync(scheme, 'utf8'), '<Scheme owner="user"/>');
});

for (const shape of ['missing', 'duplicate']) {
  test(`shared scheme rejects ${shape} App targets`, t => {
    const { project } = iosFixture(t);
    writeFileSync(project, shape === 'missing' ? 'no target here' : projectText() + projectText('ABCDEF1234567890ABCDEF12'));
    assert.throws(() => xcode.ensureSharedAppScheme(project), /App target|ambiguous/i);
  });
}

function androidFixture(t) {
  const directory = fixture(t);
  write(join(directory, 'package.json'), JSON.stringify({ dependencies: {} }));
  const android = join(directory, 'android');
  const app = write(join(android, 'app/build.gradle'), `repositories {
    flatDir{
        dirs '../capacitor-cordova-android-plugins/src/main/libs', 'libs'
    }
}
dependencies {
    implementation fileTree(include: ['*.jar'], dir: 'libs')
    implementation project(':capacitor-cordova-android-plugins')
    implementation platform('com.google.firebase:firebase-bom:34.4.0')
}
`);
  const cordova = write(join(android, 'capacitor-cordova-android-plugins/build.gradle'), `repositories {
    google()
    mavenCentral()
    flatDir{
        dirs 'src/main/libs', 'libs'
    }
}
dependencies {
    implementation fileTree(dir: 'src/main/libs', include: ['*.jar'])
    implementation "org.apache.cordova:framework:14.0.1"
}
`);
  return { directory, android, app, cordova };
}

test('unused flatDir removal preserves dependency sources and handles a sync', t => {
  const { android, app, cordova } = androidFixture(t);
  const generatedCordova = readFileSync(cordova, 'utf8');
  assert.equal(gradle.removeUnusedFlatDirRepositories(android).removed.length, 2);
  assert.doesNotMatch(readFileSync(app, 'utf8'), /flatDir\s*\{/);
  assert.match(readFileSync(app, 'utf8'), /fileTree/);
  assert.match(readFileSync(app, 'utf8'), /project\(':capacitor-cordova-android-plugins'\)/);
  assert.match(readFileSync(app, 'utf8'), /firebase-bom:34\.4\.0/);
  assert.match(readFileSync(cordova, 'utf8'), /google\(\)[\s\S]*mavenCentral\(\)/);
  assert.equal(gradle.removeUnusedFlatDirRepositories(android).removed.length, 0);
  writeFileSync(cordova, generatedCordova);
  assert.equal(gradle.removeUnusedFlatDirRepositories(android).removed.length, 1);
});

for (const repository of ['app/libs/custom.aar', 'capacitor-cordova-android-plugins/src/main/libs/custom.jar', 'capacitor-cordova-android-plugins/libs/custom.AAR']) {
  test(`local artifact refuses removal without mutating either Gradle file: ${repository}`, t => {
    const { android, app, cordova } = androidFixture(t);
    const originals = [readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')];
    write(join(android, repository), 'user library');
    assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /local artifact/i);
    assert.deepEqual([readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')], originals);
  });
}

test('a declared Cordova package refuses removal before any write', t => {
  const { directory, android, app } = androidFixture(t);
  const original = readFileSync(app, 'utf8');
  write(join(directory, 'package.json'), JSON.stringify({ dependencies: { 'cordova-example': '1.0.0' } }));
  write(join(directory, 'node_modules/cordova-example/package.json'), JSON.stringify({ cordova: { id: 'cordova-example' } }));
  assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /Cordova plugin/i);
  assert.equal(readFileSync(app, 'utf8'), original);
});

test('an unexpected repository shape refuses both writes', t => {
  const { android, app, cordova } = androidFixture(t);
  writeFileSync(cordova, readFileSync(cordova, 'utf8').replace("dirs 'src/main/libs', 'libs'", "dirs 'user-owned'"));
  const originals = [readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')];
  assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /unexpected|unrecognized/i);
  assert.deepEqual([readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')], originals);
});

test('simulator arguments preserve unsigned builds and keep metadata opt-out out of project files', async t => {
  const { project } = iosFixture(t);
  const before = readFileSync(project, 'utf8');
  const { iosSimulatorBuildArguments } = await import('../build.mjs');
  const args = iosSimulatorBuildArguments(dirname(project));
  assert.ok(args.includes('-scheme') && args.includes('App'));
  assert.ok(args.includes('generic/platform=iOS Simulator'));
  for (const setting of ['ONLY_ACTIVE_ARCH=NO', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO', 'LM_SKIP_METADATA_EXTRACTION=YES']) assert.ok(args.includes(setting), setting);
  assert.ok(!args.includes('-target'));
  assert.equal(readFileSync(project, 'utf8'), before);
});

test('an AppIntents source refuses the simulator metadata opt-out', async t => {
  const { project } = iosFixture(t, 'import AppIntents\n');
  const { iosSimulatorBuildArguments } = await import('../build.mjs');
  assert.throws(() => iosSimulatorBuildArguments(dirname(project)), /AppIntents|metadata/i);
});

test('Cordova plugin.xml is refused even without package metadata', t => {
  const { directory, android, app } = androidFixture(t);
  const original = readFileSync(app, 'utf8');
  write(join(directory, 'package.json'), JSON.stringify({ dependencies: { 'cordova-example': '1.0.0' } }));
  write(join(directory, 'node_modules/cordova-example/package.json'), '{}');
  write(join(directory, 'node_modules/cordova-example/plugin.xml'), '<plugin id="cordova-example"/>');
  assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /Cordova plugin/i);
  assert.equal(readFileSync(app, 'utf8'), original);
});

test('Android-specific includePlugins is checked before removing repositories', t => {
  const { directory, android } = androidFixture(t);
  write(join(directory, 'capacitor.config.json'), JSON.stringify({ android: { includePlugins: ['cordova-example'] } }));
  write(join(directory, 'node_modules/cordova-example/package.json'), '{}');
  write(join(directory, 'node_modules/cordova-example/plugin.xml'), '<plugin id="cordova-example"/>');
  assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /Cordova plugin/i);
});

test('a local artifact added after preparation is still refused', t => {
  const { android, app, cordova } = androidFixture(t);
  gradle.removeUnusedFlatDirRepositories(android);
  const originals = [readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')];
  write(join(android, 'app/libs/added-later.aar'), 'user library');
  assert.throws(() => gradle.removeUnusedFlatDirRepositories(android), /local artifact/i);
  assert.deepEqual([readFileSync(app, 'utf8'), readFileSync(cordova, 'utf8')], originals);
});
