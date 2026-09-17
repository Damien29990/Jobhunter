// Agent structural metadata: keys, colors, desk props, quick-action field defs.
// All human-readable text (role, bio, purpose, how-to, labels) lives in the
// i18n locale files under `agents.{key}` and `tutorial.*`.

export const AGENTS = [
  {
    key: 'milo',
    name: 'Milo',
    color: 'violet',
    accent: '#a78bfa',
    desk: 'reception',
    quickAction: {
      fields: [
        { name: 'cv_file', labelKey: 'tutorial.fields.cvFile', type: 'cvfile' },
      ],
      actionKey: 'tutorial.actions.milo',
    },
  },
  {
    key: 'rex',
    name: 'Rex',
    color: 'emerald',
    accent: '#10b981',
    desk: 'terminal',
    quickAction: {
      fields: [
        { name: 'query', labelKey: 'tutorial.fields.query', type: 'text', placeholder: 'Senior Backend Engineer Python IoT' },
        { name: 'min_score', labelKey: 'tutorial.fields.minScore', type: 'number', default: 75 },
      ],
      actionKey: 'tutorial.actions.rex',
    },
  },
  {
    key: 'dana',
    name: 'Dana',
    color: 'cyan',
    accent: '#06b6d4',
    desk: 'files',
    quickAction: {
      fields: [
        { name: 'company', labelKey: 'tutorial.fields.company', type: 'text', placeholder: 'MTR' },
        { name: 'job_id', labelKey: 'tutorial.fields.jobId', type: 'jobselect' },
        { name: 'min_score', labelKey: 'tutorial.fields.minScore', type: 'number', default: 80 },
        { name: 'force_refresh', labelKey: 'tutorial.fields.forceRefresh', type: 'checkbox', default: false },
      ],
      actionKey: 'tutorial.actions.dana',
    },
  },
  {
    key: 'leo',
    name: 'Leo',
    color: 'amber',
    accent: '#f59e0b',
    desk: 'printer',
    quickAction: {
      fields: [
        { name: 'company', labelKey: 'tutorial.fields.company', type: 'text', placeholder: 'HSBC' },
        { name: 'job_id', labelKey: 'tutorial.fields.jobId', type: 'jobselect' },
        { name: 'min_score', labelKey: 'tutorial.fields.minMatchScore', type: 'number', default: 80 },
        { name: 'template', labelKey: 'tutorial.fields.canvasTemplate', type: 'text', placeholder: 'classic | compact | technical' },
      ],
      actionKey: 'tutorial.actions.leo',
    },
  },
  {
    key: 'clara',
    name: 'Clara',
    color: 'rose',
    accent: '#f43f5e',
    desk: 'stamps',
    quickAction: {
      fields: [
        { name: 'company', labelKey: 'tutorial.fields.company', type: 'text', placeholder: 'ATAL' },
        { name: 'job_id', labelKey: 'tutorial.fields.jobId', type: 'jobselect' },
        { name: 'min_score', labelKey: 'tutorial.fields.minMatchScore', type: 'number', default: 80 },
      ],
      actionKey: 'tutorial.actions.clara',
    },
  },
]

export const AGENT_BY_KEY = Object.fromEntries(AGENTS.map((a) => [a.key, a]))

/** Floor + desk cards. Milo is opened from the header "Talk to Milo" button. */
export const OFFICE_AGENTS = AGENTS.filter((a) => a.key !== 'milo')

// Quest bar steps — one per agent, in pipeline order. Labels via i18n.
export const QUEST_STEPS = [
  { agent: 'milo', labelKey: 'quest.steps.milo' },
  { agent: 'rex', labelKey: 'quest.steps.rex' },
  { agent: 'dana', labelKey: 'quest.steps.dana' },
  { agent: 'leo', labelKey: 'quest.steps.leo' },
  { agent: 'clara', labelKey: 'quest.steps.clara' },
]
