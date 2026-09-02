// Maps each Tier 1/2 connector's raw posting shape into the PRD req. 10
// unified schema: job_id, source, title, company, location, salary,
// description, apply_url, posted_date, remote_status.

const HTML_ENTITIES = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
  "&apos;": "'",
};

function stripHtml(html) {
  if (!html) return null;
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;|&apos;/g, (m) => HTML_ENTITIES[m])
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeGreenhouse(job, company) {
  return {
    job_id: String(job.id),
    source: "greenhouse",
    title: job.title,
    company,
    location: job.location?.name || null,
    salary: null,
    description: stripHtml(job.content),
    apply_url: job.absolute_url,
    posted_date: job.updated_at || null,
    remote_status: /remote/i.test(job.location?.name || "") ? "remote" : null,
  };
}

export function normalizeLever(job, company) {
  return {
    job_id: String(job.id),
    source: "lever",
    title: job.text,
    company,
    location: job.categories?.location || null,
    salary: job.salaryRange
      ? `${job.salaryRange.min ?? ""}-${job.salaryRange.max ?? ""} ${job.salaryRange.currency ?? ""}`.trim()
      : null,
    description: job.descriptionPlain || stripHtml(job.description),
    apply_url: job.applyUrl || job.hostedUrl,
    posted_date: job.createdAt ? new Date(job.createdAt).toISOString() : null,
    remote_status: /remote/i.test(job.categories?.location || job.categories?.commitment || "")
      ? "remote"
      : null,
  };
}

export function normalizeAshby(job, company) {
  return {
    job_id: String(job.id),
    source: "ashby",
    title: job.title,
    company,
    location: job.location || null,
    salary: job.compensation?.summary || null,
    description: job.descriptionPlain || stripHtml(job.descriptionHtml),
    apply_url: job.applyUrl || job.jobUrl,
    posted_date: job.publishedAt || null,
    remote_status: job.isRemote ? "remote" : null,
  };
}

export function normalizeRemotive(job) {
  return {
    job_id: String(job.id),
    source: "remotive",
    title: job.title,
    company: job.company_name,
    location: job.candidate_required_location || null,
    salary: job.salary || null,
    description: stripHtml(job.description),
    apply_url: job.url,
    posted_date: job.publication_date || null,
    remote_status: "remote", // Remotive is remote-only by definition
  };
}

export function normalizeRemoteOK(job) {
  const salary =
    job.salary_min || job.salary_max
      ? `${job.salary_min || ""}-${job.salary_max || ""}`.trim()
      : null;
  return {
    job_id: String(job.id),
    source: "remoteok",
    title: job.position,
    company: job.company,
    location: job.location || null,
    salary,
    description: stripHtml(job.description),
    apply_url: job.apply_url || job.url,
    posted_date: job.date || null,
    remote_status: "remote", // RemoteOK is remote-only by definition
  };
}

export function normalizeWeWorkRemotely(job) {
  // WWR's RSS gives no numeric id; derive a stable one from the apply link's slug.
  const jobId = job.apply_url ? job.apply_url.replace(/\/+$/, "").split("/").pop() : job.title;
  return {
    job_id: jobId,
    source: "weworkremotely",
    title: job.title,
    company: job.company,
    location: job.location || null,
    salary: null,
    description: job.description,
    apply_url: job.apply_url,
    posted_date: job.posted_date || null,
    remote_status: "remote", // WeWorkRemotely is remote-only by definition
  };
}

// Several boards report remote in the location string rather than a flag, and
// they do not agree on the word. BMO's Workday board says
// "REMOTE/TELETRAVAIL, ON, CAN" on a bilingual posting.
const REMOTE_TEXT = /\bremote\b|t[ée]l[ée]travail|work from home|anywhere in canada/i;

// Recruitee stamps dates as "2026-08-26 06:19:46 UTC", which Date() will not
// parse. Everything downstream expects ISO 8601.
function isoFromUtcStamp(value) {
  if (!value) return null;
  const text = String(value).trim();
  const d = new Date(/UTC$/i.test(text) ? text.replace(/\s+UTC$/i, "Z").replace(" ", "T") : text);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function normalizeWorkday(job, company) {
  // The list endpoint says "3 Locations" for a multi-city posting; the detail
  // pass replaces that with the real one when it ran.
  const location = job.__location || job.locationsText || null;
  return {
    // bulletFields carries the requisition id (R0017705), which is stable
    // across re-postings in a way the URL path is not.
    job_id: String(job.bulletFields?.[0] || job.externalPath || job.title),
    source: "workday",
    title: job.title,
    company: job.__company || company,
    location: /^\d+\s+Locations?$/i.test(location || "") ? null : location,
    salary: null,
    description: stripHtml(job.__description),
    apply_url: job.__applyUrl,
    // startDate is a real ISO date from the detail pass; __postedDate is
    // parsed back out of "Posted 3 Days Ago" when only the list ran.
    posted_date: job.__startDate || job.__postedDate || null,
    remote_status: REMOTE_TEXT.test(location || "") ? "remote" : null,
  };
}

export function normalizeWorkable(job, company) {
  const first = job.locations?.[0];
  const location =
    [job.city || first?.city, job.state || first?.region, job.country || first?.country]
      .filter(Boolean)
      .join(", ") || null;
  return {
    job_id: String(job.shortcode || job.id),
    source: "workable",
    title: job.title,
    company: job.__company || company,
    location,
    salary: null,
    description: stripHtml(job.description),
    apply_url: job.application_url || job.url || job.shortlink,
    posted_date: job.published_on || job.created_at || null,
    remote_status: job.telecommuting || REMOTE_TEXT.test(location || "") ? "remote" : null,
  };
}

export function normalizeRecruitee(job, company) {
  const location =
    job.location || [job.city, job.state_name, job.country].filter(Boolean).join(", ") || null;
  // Recruitee splits the posting body across two fields and boards use them
  // inconsistently; the experience cap needs to see both.
  const body = [job.description, job.requirements].filter(Boolean).join(" ");
  return {
    job_id: String(job.id),
    source: "recruitee",
    title: job.title,
    company: job.__company || job.company_name || company,
    location,
    salary: job.salary?.min ? `${job.salary.min}-${job.salary.max ?? ""} ${job.salary.currency ?? ""}`.trim() : null,
    description: stripHtml(body),
    apply_url: job.careers_apply_url || job.careers_url,
    posted_date: isoFromUtcStamp(job.published_at || job.created_at),
    // The one board here that states remote as a boolean instead of leaving it
    // to be regexed out of a location string.
    remote_status: job.remote ? "remote" : null,
  };
}

export function normalizeBambooHR(job, company) {
  const location = [job.location?.city, job.location?.state].filter(Boolean).join(", ") || null;
  return {
    job_id: String(job.id),
    source: "bamboohr",
    title: job.jobOpeningName,
    company: job.__company || company,
    location,
    salary: null,
    description: stripHtml(job.__description),
    apply_url: job.__applyUrl,
    posted_date: job.__datePosted || null,
    remote_status: job.isRemote || REMOTE_TEXT.test(location || "") ? "remote" : null,
  };
}

export function normalizeCareerPage(job, fallbackCompany) {
  const address = job.jobLocation?.address;
  const location = address
    ? [address.addressLocality, address.addressRegion].filter(Boolean).join(", ") || null
    : null;
  const salaryValue = job.baseSalary?.value;
  const salary = salaryValue
    ? `${salaryValue.value ?? salaryValue.minValue ?? ""}${
        salaryValue.maxValue ? "-" + salaryValue.maxValue : ""
      } ${job.baseSalary?.currency ?? ""}`.trim()
    : null;
  const applyUrl = job.url || job.__pageUrl;

  return {
    job_id: job.identifier?.value || applyUrl || `${fallbackCompany}-${job.title}`,
    source: "careerpage",
    title: job.title,
    company: job.hiringOrganization?.name || fallbackCompany,
    location,
    salary,
    description: stripHtml(job.description),
    apply_url: applyUrl,
    posted_date: job.datePosted || null,
    remote_status: job.jobLocationType === "TELECOMMUTE" ? "remote" : null,
  };
}

const NORMALIZERS = {
  greenhouse: normalizeGreenhouse,
  lever: normalizeLever,
  ashby: normalizeAshby,
  workday: normalizeWorkday,
  workable: normalizeWorkable,
  recruitee: normalizeRecruitee,
  bamboohr: normalizeBambooHR,
  remotive: normalizeRemotive,
  remoteok: normalizeRemoteOK,
  weworkremotely: normalizeWeWorkRemotely,
  careerpage: normalizeCareerPage,
};

export function normalize(source, rawJob, company) {
  const fn = NORMALIZERS[source];
  if (!fn) throw new Error(`no normalizer for source: ${source}`);
  return fn(rawJob, company);
}
