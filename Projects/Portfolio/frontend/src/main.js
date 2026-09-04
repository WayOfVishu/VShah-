/** Entry point.
 *
 *  Content is imported, not fetched — Vite resolves @data to the backend's
 *  data directory and inlines these files at build time. The page therefore
 *  paints complete on the first script evaluation, with no loading state, no
 *  layout shift, and no dependency on the API being up.
 *
 *  The API is used by exactly one thing: the live demo. */

import './styles/main.css';

import profile from '@data/profile.json';
import projects from '@data/projects.json';
import experience from '@data/experience.json';
import skills from '@data/skills.json';
import educationData from '@data/education.json';

import { $ } from './lib/dom.js';
import { initReveals, initCounters, initNav, initClock, initCardGlow } from './lib/motion.js';
import { initField } from './gl/field.js';
import { mountRemoteClassifier } from './demos/remoteClassifier.js';
import { mountTelemetry } from './demos/telemetry.js';
import {
  renderNav,
  renderHero,
  renderProjects,
  renderExperience,
  renderSkills,
  renderEducation,
  renderContact,
  renderFooter,
} from './sections/render.js';

document.documentElement.classList.remove('no-js');

const ordered = [...projects].sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

/* ---- paint ---- */

renderNav($('.nav'), profile);
renderHero($('#top'), profile);
renderProjects($('#projects-grid'), ordered);
renderExperience($('#timeline'), experience);
renderSkills($('#skills-grid'), skills);
renderEducation($('#education-grid'), educationData);
renderContact($('#contact'), profile);
renderFooter($('.footer'), profile);

/* ---- demos ---- */

mountRemoteClassifier($('#demo-remote'));
mountTelemetry($('#demo-telemetry'));

/* ---- behaviour ---- */
// Run after paint so the observers measure final layout, not a half-built DOM.

requestAnimationFrame(() => {
  initReveals();
  initCounters();
  initCardGlow();
  initNav();
  initClock($('#clock'), profile.timezone);

  const canvas = $('#field');
  if (canvas) initField(canvas);
});
