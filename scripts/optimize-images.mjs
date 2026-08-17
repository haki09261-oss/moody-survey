import { stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const assets = join(root, 'assets');
const web = join(root, 'web');
const jobs = [
  ['universal-survey-background.png', 'universal-survey-background.webp'],
  ['reward-page-clean.png', 'reward-page-clean.webp'],
  ['moody-ip.png', 'moody-ip-mobile.webp', 800],
  ['q7-product-m.png', 'q7-product-m-mobile.webp', 1200],
  ['q7-product-air.png', 'q7-product-air-mobile.webp', 1200],
  ['q7-product-s.png', 'q7-product-s-mobile.webp', 1200],
  ['moody-logo-original.png', 'moody-logo-original.webp', 800]
];

for (const [inputName, outputName, width] of jobs) {
  const input = join(assets, inputName);
  const output = join(assets, outputName);
  const before = (await stat(input)).size;
  let pipeline = sharp(input, { limitInputPixels: false }).rotate();
  if (width) pipeline = pipeline.resize({ width, withoutEnlargement: true });
  await pipeline.webp({ quality: 88, alphaQuality: 100, effort: 6, smartSubsample: true }).toFile(output);
  const after = (await stat(output)).size;
  console.log(`${inputName} -> ${outputName}: ${(before / 1024).toFixed(0)}KB -> ${(after / 1024).toFixed(0)}KB`);
}

const webJobs = [
  ['survey-question-bg.png', 'survey-question-bg.webp'],
  ['survey-plain-empty-bg.png', 'survey-plain-empty-bg.webp'],
];

for (const [inputName, outputName] of webJobs) {
  const input = join(web, inputName);
  const output = join(web, outputName);
  const before = (await stat(input)).size;
  await sharp(input, { limitInputPixels: false })
    .rotate()
    .webp({ quality: 86, alphaQuality: 100, effort: 6, smartSubsample: true })
    .toFile(output);
  const after = (await stat(output)).size;
  console.log(`${inputName} -> ${outputName}: ${(before / 1024).toFixed(0)}KB -> ${(after / 1024).toFixed(0)}KB`);
}
