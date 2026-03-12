/**
 * Validate JSON structure of all translation files
 */
const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '..', 'apps', 'web', 'locales');
const langs = ['fr', 'en', 'es', 'de', 'it'];

console.log('Validating translation files...\n');

let allValid = true;

langs.forEach(lang => {
  const filePath = path.join(LOCALES_DIR, lang, 'translation.json');

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);
    const keys = Object.keys(data);

    console.log(`✓ ${lang.toUpperCase()}: Valid JSON - ${keys.length} top-level sections`);
    console.log(`  Sections: ${keys.join(', ')}`);

    // Check for required sections
    const requiredSections = ['auth', 'chat', 'settings', 'hitl', 'account_inactive'];
    const missingSections = requiredSections.filter(s => !keys.includes(s));

    if (missingSections.length > 0) {
      console.log(`  ⚠ Missing sections: ${missingSections.join(', ')}`);
      allValid = false;
    }

  } catch(e) {
    console.log(`✗ ${lang.toUpperCase()}: ERROR - ${e.message}`);
    allValid = false;
  }

  console.log('');
});

if (allValid) {
  console.log('✅ All translation files are valid!\n');
  process.exit(0);
} else {
  console.log('❌ Some translation files have issues.\n');
  process.exit(1);
}
