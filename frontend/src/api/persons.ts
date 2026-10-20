export interface PersonSummary {
  id: number
  name: string
  note: string
  sample_count: number
  created_at: string
}

export interface PersonDetail extends PersonSummary {
  samples: {
    id: number
    dimensions: number
    capture_id: string
    model_fingerprint: string
    image_url: string
    quality: { mean_brightness: number; sharpness: number; detection_confidence: number }
  }[]
}

export interface PersonDeletion {
  deleted: number | number[]
  cleanup: { deleted_files: number; pending_files: number }
}

export function registrationForm(person: { name: string; note: string; files: File[] }) {
  const form = new FormData()
  form.append('name', person.name.trim())
  form.append('note', person.note.trim())
  form.append('capture_id', `enroll-${crypto.randomUUID()}`)
  person.files.forEach((file) => form.append('files', file))
  return form
}
