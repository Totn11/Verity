import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Camera, UserRound, X } from "lucide-react";
import type { Person } from "../data/mockData";
import type { PersonInput } from "../data/PeopleContext";

type Props = {
  person?: Person;
  onClose: () => void;
  onSave: (person: PersonInput) => void | Promise<void>;
  existingIds: string[];
};

export default function PersonEditorDialog({ person, onClose, onSave, existingIds }: Props) {
  const [name, setName] = useState(person?.name ?? "");
  const [id, setId] = useState(person?.id ?? "");
  const [department, setDepartment] = useState(person?.department ?? "");
  const [role, setRole] = useState(person?.role ?? "");
  const [email, setEmail] = useState(person?.email ?? "");
  const [phone, setPhone] = useState(person?.phone ?? "");
  const [registrationStatus, setRegistrationStatus] = useState<Person["registrationStatus"]>(person?.registrationStatus ?? "Active");
  const [attendanceStatus] = useState<Person["status"]>(person?.status ?? "Absent");
  const [avatar, setAvatar] = useState(person?.avatar ?? "");
  const [photoError, setPhotoError] = useState("");
  const [formError, setFormError] = useState("");

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  function handlePhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setPhotoError("");
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setPhotoError("Choose an image file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setPhotoError("Image must be 5 MB or smaller.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setAvatar(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => setPhotoError("Could not read this image. Please try another file.");
    reader.readAsDataURL(file);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedId = id.trim().toUpperCase();
    if (!person && existingIds.includes(normalizedId)) {
      setFormError("That ID is already registered.");
      return;
    }
    const trimmedName = name.trim();
    if (!trimmedName || !normalizedId || !department.trim() || !role.trim() || !email.trim() || !phone.trim()) {
      setFormError("Complete all required fields.");
      return;
    }
    const initials = trimmedName.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    setFormError("");
    try {
      await onSave({ name: trimmedName, id: normalizedId, department: department.trim(), role: role.trim(), email: email.trim(), phone: phone.trim(), registrationStatus, status: attendanceStatus, avatar, initials });
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save this person.");
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="person-dialog" role="dialog" aria-modal="true" aria-labelledby="person-dialog-title">
        <div className="dialog-heading"><div><span className="eyebrow">{person ? "PEOPLE DIRECTORY" : "AUTHORIZED REGISTRATION"}</span><h2 id="person-dialog-title">{person ? "Edit person" : "Register a person"}</h2><p>Only collect information required for facility administration.</p></div><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
        <form onSubmit={submit}>
          <div className="photo-upload-row">
            <span className="avatar avatar-lg">{avatar ? <img src={avatar} alt="Selected profile" /> : <UserRound size={24} />}</span>
            <div><strong>Profile photo <span>(optional)</span></strong><small>Preview only; uploads are not saved to the facility API or used for identity matching.</small><label className="button button-secondary upload-photo"><Camera size={14} /> Choose image<input type="file" accept="image/*" onChange={handlePhoto} /></label>{photoError && <small className="form-error">{photoError}</small>}</div>
          </div>
          <div className="editor-form-grid">
            <label className="form-row">Full name<input autoFocus value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} placeholder="Full name" /></label>
            <label className="form-row">Employee / student ID<input value={id} onChange={(event) => setId(event.target.value)} required maxLength={32} placeholder="e.g. VR-2057" disabled={Boolean(person)} /></label>
            <label className="form-row">Department / unit<input value={department} onChange={(event) => setDepartment(event.target.value)} required maxLength={80} placeholder="Department" /></label>
            <label className="form-row">Role<input value={role} onChange={(event) => setRole(event.target.value)} required maxLength={80} placeholder="Role or position" /></label>
            <label className="form-row">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={320} placeholder="name@example.com" /></label>
            <label className="form-row">Phone<input type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} required maxLength={64} placeholder="Phone number" /></label>
            <label className="form-row editor-status">Registration status<select value={registrationStatus} onChange={(event) => setRegistrationStatus(event.target.value as Person["registrationStatus"])}><option>Active</option><option>Inactive</option></select></label>
          </div>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <div className="dialog-actions"><button className="button button-secondary" type="button" onClick={onClose}>Cancel</button><button className="button button-primary" type="submit">{person ? "Save changes" : "Register person"}</button></div>
        </form>
      </section>
    </div>
  );
}
