import { useEffect, useState } from "react";
import {
  getResumeProfile,
  rebuildResumeProfile,
  saveResumeProfile,
  type ProfileEducation,
  type ProfileSkill,
  type ResumeProfile,
} from "../../services/api";

interface ProfilePanelProps {
  resumeId: number | null;
  onClose: () => void;
}

const LEVELS: ProfileEducation["level"][] = ["phd", "master", "bachelor", "diploma", "other"];
const INPUT =
  "rounded border border-[#353535] bg-[#262626] px-2 py-1 text-xs text-[#F5F5F5] focus:border-[#666666] focus:outline-none";
const BUTTON =
  "rounded border border-[#353535] px-2 py-1 text-xs hover:bg-[#353535] disabled:cursor-not-allowed disabled:opacity-40";

/** "" -> null, "5" -> 5; invalid text -> undefined (rejected on save). */
function parseYears(value: string): number | null | undefined {
  const v = value.trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 60 ? n : undefined;
}

export default function ProfilePanel({ resumeId, onClose }: ProfilePanelProps) {
  const [profile, setProfile] = useState<ResumeProfile | null>(null);
  const [skills, setSkills] = useState<{ name: string; years: string }[]>([]);
  const [totalYears, setTotalYears] = useState("");
  const [education, setEducation] = useState<ProfileEducation[]>([]);
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function show(p: ResumeProfile) {
    setProfile(p);
    setSkills(p.skills.map((s) => ({ name: s.name, years: s.years == null ? "" : String(s.years) })));
    setTotalYears(p.total_experience_years == null ? "" : String(p.total_experience_years));
    setEducation(p.education.map((e) => ({ ...e })));
    setRole(p.current_role ?? "");
  }

  useEffect(() => {
    if (resumeId == null) return;
    let active = true;
    setBusy("Reading your resume...");
    setError("");
    getResumeProfile(resumeId)
      .then((p) => active && show(p))
      .catch((exc) => active && setError(exc instanceof Error ? exc.message : "Could not load the profile."))
      .finally(() => active && setBusy(""));
    return () => {
      active = false;
    };
  }, [resumeId]);

  async function save() {
    if (resumeId == null) return;
    const parsedSkills: ProfileSkill[] = [];
    for (const s of skills) {
      if (!s.name.trim()) continue;
      const years = parseYears(s.years);
      if (years === undefined) {
        setError(`Years for "${s.name}" must be a number from 0 to 60, or empty.`);
        return;
      }
      parsedSkills.push({ name: s.name.trim(), years });
    }
    const total = parseYears(totalYears);
    if (total === undefined) {
      setError("Total experience must be a number from 0 to 60, or empty.");
      return;
    }
    setBusy("Saving...");
    setError("");
    setNotice("");
    try {
      show(
        await saveResumeProfile(resumeId, {
          skills: parsedSkills,
          total_experience_years: total,
          education: education.filter((e) => e.degree.trim() || e.field.trim()),
          current_role: role.trim() || null,
        }),
      );
      setNotice("Saved. Matching and screening answers now use this profile.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save the profile.");
    } finally {
      setBusy("");
    }
  }

  async function reread() {
    if (resumeId == null) return;
    const overwrite = Boolean(profile?.edited_by_user);
    if (overwrite && !window.confirm("Read the resume again? This replaces your edits.")) return;
    setBusy("Reading your resume...");
    setError("");
    setNotice("");
    try {
      show(await rebuildResumeProfile(resumeId, overwrite));
      setNotice("The profile was read again from your resume.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not read the resume.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section
      aria-label="Resume profile"
      className="flex h-full min-h-0 flex-col overflow-hidden bg-[#171717] text-[#F5F5F5]"
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-[#353535] px-4 py-2 text-sm">
        <span className="font-medium">Resume profile</span>
        {profile?.edited_by_user && <span className="text-xs text-[#A3A3A3]">(edited by you)</span>}
        <span className="flex-1" />
        <button type="button" onClick={() => void reread()} disabled={!!busy || resumeId == null} className={BUTTON}>
          Read resume again
        </button>
        <button type="button" onClick={() => void save()} disabled={!!busy || !profile} className={BUTTON}>
          Save
        </button>
        <button type="button" onClick={onClose} className={BUTTON}>
          Close
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-xs">
        {resumeId == null && <p className="text-[#A3A3A3]">Upload a resume first.</p>}
        {busy && <p className="mb-2 text-[#A3A3A3]">{busy}</p>}
        {error && <p className="mb-2 text-red-400">{error}</p>}
        {notice && <p className="mb-2 text-green-300">{notice}</p>}

        {profile && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-4">
              <label className="flex flex-col gap-1">
                <span className="text-[#A3A3A3]">Current role</span>
                <input value={role} onChange={(e) => setRole(e.target.value)} className={`${INPUT} w-64`} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[#A3A3A3]">Total experience (years)</span>
                <input
                  value={totalYears}
                  onChange={(e) => setTotalYears(e.target.value)}
                  inputMode="decimal"
                  className={`${INPUT} w-24`}
                />
              </label>
            </div>

            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="font-medium">Skills ({skills.length})</span>
                <span className="text-[#A3A3A3]">
                  Years per skill are used for screening answers. Empty means the question is asked.
                </span>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_5rem_auto] gap-1 sm:grid-cols-[minmax(0,1fr)_5rem_auto_minmax(0,1fr)_5rem_auto]">
                {skills.map((s, i) => (
                  <div key={i} className="contents">
                    <input
                      aria-label="Skill"
                      value={s.name}
                      onChange={(e) =>
                        setSkills((all) => all.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                      }
                      className={INPUT}
                    />
                    <input
                      aria-label={`Years with ${s.name || "skill"}`}
                      placeholder="years"
                      value={s.years}
                      inputMode="decimal"
                      onChange={(e) =>
                        setSkills((all) => all.map((x, j) => (j === i ? { ...x, years: e.target.value } : x)))
                      }
                      className={INPUT}
                    />
                    <button
                      type="button"
                      aria-label={`Remove ${s.name || "skill"}`}
                      onClick={() => setSkills((all) => all.filter((_, j) => j !== i))}
                      className="px-1 text-[#A3A3A3] hover:text-red-300"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setSkills((all) => [...all, { name: "", years: "" }])}
                className={`${BUTTON} mt-2`}
              >
                Add skill
              </button>
            </div>

            <div>
              <span className="mb-1 block font-medium">Education</span>
              <div className="flex flex-col gap-1">
                {education.map((e, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-1">
                    <input
                      aria-label="Degree"
                      placeholder="Degree"
                      value={e.degree}
                      onChange={(ev) =>
                        setEducation((all) => all.map((x, j) => (j === i ? { ...x, degree: ev.target.value } : x)))
                      }
                      className={`${INPUT} w-56`}
                    />
                    <select
                      aria-label="Level"
                      value={e.level}
                      onChange={(ev) =>
                        setEducation((all) =>
                          all.map((x, j) =>
                            j === i ? { ...x, level: ev.target.value as ProfileEducation["level"] } : x,
                          ),
                        )
                      }
                      className={INPUT}
                    >
                      {LEVELS.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Field"
                      placeholder="Field"
                      value={e.field}
                      onChange={(ev) =>
                        setEducation((all) => all.map((x, j) => (j === i ? { ...x, field: ev.target.value } : x)))
                      }
                      className={`${INPUT} w-48`}
                    />
                    <button
                      type="button"
                      aria-label="Remove education"
                      onClick={() => setEducation((all) => all.filter((_, j) => j !== i))}
                      className="px-1 text-[#A3A3A3] hover:text-red-300"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setEducation((all) => [...all, { degree: "", level: "bachelor", field: "" }])}
                className={`${BUTTON} mt-2`}
              >
                Add education
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
