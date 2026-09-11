// Resume fit: how much of what a posting asks for your resume already names.
//
// Everything else in match_score comes from stated preferences — where you want
// to work, which titles, which level. That answers "is this a job I want", not
// "is this a job I'd hear back from". Resume fit adds the second question as a
// minority share of the score (scoring.resumeWeight in preferences.json), so
// preferences stay primary and the resume mostly reorders postings the
// preferences already rate about the same.
//
// A dictionary match rather than an LLM call or an embedding: every run
// re-scores the whole table (lib/rescore.js), it has to work with no network,
// and a ranking you can't explain is one you can't argue with. The SAME
// vocabulary judges both sides, which is what makes "the posting names 10
// skills and your resume names 7 of them" a real comparison instead of two
// unrelated keyword counts. A skill missing from this list is invisible on both
// sides — so if you learn something new, add it here as well as to the resume.

import { readFileSync, existsSync } from "node:fs";
import { BASE_RESUME_PATH } from "./promptBuild.js";

// [label, ...patterns]. A string is a case-insensitive phrase matched as a
// whole token (spaces also match hyphens, so "delta lake" hits "Delta-Lake").
// A RegExp is used as-is — that is how the ambiguous words are handled: "Go",
// "Spark", "REST", "SAP" and "React" only count capitalized, because in
// lowercase they are ordinary English ("go", "spark joy", "the rest of").
export const SKILLS = [
  // Languages
  ["Python", "python"],
  ["TypeScript", "typescript"],
  ["JavaScript", "javascript", /(?<![A-Za-z0-9])JS(?![A-Za-z0-9])/],
  // Bounded on letters, so NoSQL, MySQL and PostgreSQL don't count as SQL.
  ["SQL", "sql"],
  ["Java", "java"],
  ["Kotlin", "kotlin"],
  ["Scala", "scala"],
  // "Go-to-market" and "go-live" are not the language.
  ["Go", "golang", /(?<![A-Za-z0-9])Go(?![A-Za-z0-9-])/],
  ["Rust", "rust"],
  ["C++", "c++", "cpp"],
  ["C# / .NET", "c#", ".net", "asp.net", "dotnet"],
  ["Ruby", "ruby", "ruby on rails"],
  ["PHP", "php"],
  ["Swift", /(?<![A-Za-z0-9])Swift(?![A-Za-z0-9])/],
  ["Bash / shell", "bash", "shell scripting", "powershell"],
  ["ABAP", "abap"],
  ["MATLAB", "matlab"],

  // Data engineering
  ["ETL / ELT", "etl", "elt"],
  ["Data pipelines", "data pipeline", "data pipelines"],
  ["Airflow", "airflow"],
  ["dbt", "dbt"],
  ["Fivetran", "fivetran"],
  ["Spark", "pyspark", "apache spark", "spark sql", /(?<![A-Za-z0-9])Spark(?![A-Za-z0-9])/],
  ["Kafka", "kafka"],
  ["Flink", "flink"],
  ["Databricks", "databricks"],
  ["Delta Lake", "delta lake"],
  ["Unity Catalog", "unity catalog"],
  ["Snowflake", "snowflake"],
  ["BigQuery", "bigquery"],
  ["Redshift", "redshift"],
  ["Data warehousing", "data warehouse", "data warehouses", "data warehousing"],
  ["Lakehouse / data lake", "lakehouse", "data lake", "data lakes"],
  ["Data modeling", "data modeling", "data modelling", "dimensional modeling", "dimensional modelling"],
  ["Data quality", "data quality", "data validation", "great expectations"],
  [
    "Incremental processing / CDC",
    "change data capture",
    /(?<![A-Za-z0-9])incremental\s+(?:data\s+)?(?:processing|loads?|syncs?|ingestion)(?![A-Za-z0-9])/i,
  ],
  ["Stream processing", "stream processing", "streaming data", "event streaming"],
  ["Time series", "time series"],
  ["Event sourcing", "event sourcing", "event sourced"],
  ["pandas", "pandas"],
  ["NumPy", "numpy"],
  ["PostgreSQL", "postgresql", "postgres"],
  ["MySQL", "mysql"],
  ["MongoDB", "mongodb", "mongo"],
  ["Redis", "redis"],
  ["Elasticsearch", "elasticsearch", "opensearch"],
  ["DynamoDB", "dynamodb"],
  ["Cassandra", "cassandra"],
  ["NoSQL", "nosql"],
  ["Hadoop", "hadoop", "hdfs"],
  ["Trino / Presto", "trino", "presto"],
  ["Looker", "looker"],
  ["Tableau", "tableau"],
  ["Power BI", "power bi", "powerbi"],
  ["SAP", /(?<![A-Za-z0-9])SAP(?![A-Za-z0-9])/, "s/4hana", "bw/4hana"],
  ["OData", "odata"],

  // APIs and backend
  ["REST APIs", "restful", "rest api", "rest apis", /(?<![A-Za-z0-9])REST(?![A-Za-z0-9])/],
  ["GraphQL", "graphql"],
  ["gRPC", "grpc"],
  ["Microservices", "microservices", "microservice"],
  ["Node.js", "node.js", "nodejs"],
  ["NestJS", "nestjs"],
  ["Express", "express.js", "expressjs"],
  ["Django", "django"],
  ["Flask", "flask"],
  ["FastAPI", "fastapi"],
  ["Spring Boot", "spring boot"],

  // Frontend and mobile
  ["React", "reactjs", "react.js", /(?<![A-Za-z0-9])React(?![A-Za-z0-9])/],
  ["Next.js", "next.js", "nextjs"],
  ["Angular", "angular"],
  ["Vue", "vue", "vue.js", "vuejs"],
  ["HTML / CSS", "html", "html5", "css", "css3"],
  ["iOS", /(?<![A-Za-z0-9])iOS(?![A-Za-z0-9])/],
  ["Android", "android"],
  ["React Native", "react native"],
  ["Flutter", "flutter"],

  // Machine learning and AI
  ["Machine learning", "machine learning"],
  ["Deep learning", "deep learning", "neural network", "neural networks"],
  ["Computer vision", "computer vision"],
  ["OpenCV", "opencv"],
  ["YOLO", /(?<![A-Za-z0-9])yolo(?:v\d+)?(?![A-Za-z0-9])/i],
  ["PyTorch", "pytorch"],
  ["TensorFlow", "tensorflow", "tflite", "tf lite"],
  ["Keras", "keras"],
  ["scikit-learn", "scikit learn", "sklearn"],
  ["Gradient boosting", "xgboost", "lightgbm", "catboost"],
  ["LLMs", "llm", "llms", "large language model", "large language models", "generative ai", "genai"],
  ["RAG", "retrieval augmented generation", /(?<![A-Za-z0-9])RAG(?![A-Za-z0-9])/],
  ["AI agents", "agentic", "ai agents", "llm agents", "multi agent"],
  ["LLM orchestration", "llm orchestration", "langchain", "langgraph", "llamaindex"],
  ["NLP", "nlp", "natural language processing"],
  ["Vector search", "vector database", "vector databases", "vector search", "embeddings"],
  ["MLOps", "mlops", "ml ops", "model deployment", "model serving"],
  ["Edge ML", "edge inference", "edge ai", "edge computing", "edge devices", "on device", "embedded ml", "tinyml", "raspberry pi", "jetson"],
  ["Model optimization", "model optimization", "model optimisation", "quantization", "onnx", "tensorrt"],
  ["CUDA", "cuda"],
  ["Reinforcement learning", "reinforcement learning"],
  ["MLflow", "mlflow"],
  ["Kubeflow", "kubeflow"],
  ["SageMaker", "sagemaker"],
  ["Vertex AI", "vertex ai"],
  ["Hugging Face", "hugging face", "huggingface"],
  ["JAX", /(?<![A-Za-z0-9])JAX(?![A-Za-z0-9])/],

  // Cloud and DevOps
  ["AWS", "aws", "amazon web services"],
  ["Azure", "azure"],
  ["GCP", "gcp", "google cloud"],
  ["Kubernetes", "kubernetes", "k8s"],
  ["Docker", "docker", "containerization", "containerized"],
  ["Terraform / IaC", "terraform", "infrastructure as code", "pulumi", "cloudformation", /(?<![A-Za-z0-9])IaC(?![A-Za-z0-9])/],
  ["CI/CD", "ci/cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment"],
  ["Azure DevOps", "azure devops"],
  ["GitHub Actions", "github actions"],
  ["Jenkins", "jenkins"],
  ["Git", "git"],
  ["Linux", "linux", "unix"],
  // Capitalized only: "at the helm" is not the Kubernetes package manager.
  ["Helm", /(?<![A-Za-z0-9])Helm(?![A-Za-z0-9])/],
  ["Ansible", "ansible"],
  ["Serverless", "serverless", "aws lambda", "cloud functions", "azure functions"],
  ["Observability", "observability", "prometheus", "grafana", "datadog", "opentelemetry"],
  ["Secrets management", "key vault", "secrets management", "hashicorp vault"],

  // Security and testing
  ["Application security", "application security", "appsec", "owasp", "secure coding", "input validation", "access control"],
  // Also catches the resume's own "Unit/Service-Level Testing".
  ["Unit testing", /(?<![A-Za-z0-9])unit(?:[\s-]|\/[\w-]+\s)test/i, "pytest", "jest", "test automation"],

  // Asks that rule a posting out as much as in
  ["Embedded / firmware", "firmware", "embedded c", "rtos", "microcontroller", "microcontrollers"],
  ["FPGA / HDL", "fpga", "verilog", "vhdl", "systemverilog"],
  ["Salesforce", "salesforce"],
  ["ServiceNow", "servicenow"],
];

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Letters and digits on either side end a token; punctuation does not. That is
// why "java" misses "JavaScript", "c#" hits "C#," and ".net" hits ".NET 8" —
// \b would get all three of those wrong.
function compilePhrase(phrase) {
  const body = phrase.trim().split(/\s+/).map(escapeRegExp).join("[\\s-]+");
  return new RegExp(`(?<![A-Za-z0-9])${body}(?![A-Za-z0-9])`, "i");
}

// Each phrase also carries a plain-substring needle, checked first. Most of the
// ~150 patterns never occur in a given posting, and `includes` rejects them
// far cheaper than a lookbehind regex — this is what keeps re-scoring a
// thousand stored postings on every run from being the slow part of it.
function compileSkills(skills) {
  return skills.map(([label, ...patterns]) => ({
    label,
    tests: patterns.map((p) =>
      p instanceof RegExp ? { needle: null, re: p } : { needle: p.trim().split(/\s+/)[0].toLowerCase(), re: compilePhrase(p) }
    ),
  }));
}

const COMPILED = compileSkills(SKILLS);

// Labels of every vocabulary skill the text names, in vocabulary order.
export function findSkills(text, compiled = COMPILED) {
  const raw = String(text || "");
  if (!raw) return [];
  const lower = raw.toLowerCase();
  return compiled
    .filter(({ tests }) => tests.some(({ needle, re }) => (needle === null || lower.includes(needle)) && re.test(raw)))
    .map(({ label }) => label);
}

export function profileFromText(text, source = null) {
  return { source, skills: new Set(findSkills(text)) };
}

let cached = { path: null, profile: undefined };

// The resume's skills, read once per process. null when there is no resume at
// all (it is git-ignored, so a fresh clone has none) — resume fit then simply
// doesn't apply, and match_score is the preference score unchanged.
export function loadResumeProfile({ resumePath = BASE_RESUME_PATH, reload = false } = {}) {
  if (!reload && cached.path === resumePath && cached.profile !== undefined) return cached.profile;
  const profile = existsSync(resumePath) ? profileFromText(readFileSync(resumePath, "utf8"), resumePath) : null;
  cached = { path: resumePath, profile };
  return profile;
}

// Only touches the disk when resume fit is switched on, so code (and tests)
// that never configured it never read a resume.
export function defaultResumeProfile(prefs) {
  return prefs?.resumeWeight > 0 ? loadResumeProfile() : null;
}

// How quickly the "how many do you have" half saturates: 4 matched skills
// reach 63% of it, 8 reach 86%.
const SATURATION = 4;

// 0-1, or null when the posting names no skill in the vocabulary — "we can't
// tell" is not the same as "bad fit", and a zero there would sink every posting
// with a thin description.
//
// Two halves, because each alone is wrong in a common case:
//   * coverage — the share of the posting's asks you have. Alone, it punishes
//     the kitchen-sink posting that lists 25 technologies, where having 12 is
//     a strong match. Smoothed (+1/+2) so a one-skill posting can't swing it
//     to 0 or 1 on the strength of a single word.
//   * depth — how many of its asks you have, saturating. Alone, it ignores
//     what you're missing entirely.
export function resumeFit(job, profile) {
  if (!profile) return { score: null, have: [], missing: [] };
  const asked = findSkills([job.title, job.description].filter(Boolean).join("\n"));
  if (asked.length === 0) return { score: null, have: [], missing: [] };

  const have = asked.filter((s) => profile.skills.has(s));
  const missing = asked.filter((s) => !profile.skills.has(s));
  const coverage = (have.length + 1) / (asked.length + 2);
  const depth = 1 - Math.exp(-have.length / SATURATION);
  return { score: Number((0.5 * coverage + 0.5 * depth).toFixed(4)), have, missing };
}
