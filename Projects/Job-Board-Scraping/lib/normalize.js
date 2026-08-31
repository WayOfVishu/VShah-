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
