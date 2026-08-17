"use client";

import { UserPlus } from "lucide-react";
import { useState } from "react";
import { createUser, updateUser } from "@/lib/api";
import type { AdminUser, Role } from "@/lib/types";
import { useCurrentUser } from "./user-context";

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "ais_officer", label: "AIS Officer" },
  { value: "ais_specialist", label: "AIS Specialist" },
  { value: "nof_manager", label: "NOF Manager" },
  { value: "qms_auditor", label: "QMS Auditor" },
  { value: "system_admin", label: "System Administrator" }
];

export function AdminConsole({ initialUsers }: { initialUsers: AdminUser[] }) {
  const currentUser = useCurrentUser();
  const [users, setUsers] = useState(initialUsers);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", role: "ais_officer" as Role, organization: "", password: "" });

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setCreating(true);
    try {
      const created = await createUser(form);
      setUsers((current) => [...current, created]);
      setForm({ email: "", full_name: "", role: "ais_officer", organization: "", password: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user.");
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (user: AdminUser) => {
    setError(null);
    setBusyId(user.id);
    try {
      const updated = await updateUser(user.id, { is_active: !user.is_active });
      setUsers((current) => current.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update user.");
    } finally {
      setBusyId(null);
    }
  };

  const changeRole = async (user: AdminUser, role: Role) => {
    setError(null);
    setBusyId(user.id);
    try {
      const updated = await updateUser(user.id, { role });
      setUsers((current) => current.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update user.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <section className="panel admin-create-panel">
        <div className="panel-heading"><div><h2>Create user</h2><p>New accounts are audited like every other action</p></div></div>
        <form className="intake-fields" onSubmit={submitCreate}>
          <label>Full name<input required value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} /></label>
          <label>Email<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as Role })}>
            {ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select></label>
          <label>Organization<input value={form.organization} onChange={(event) => setForm({ ...form, organization: event.target.value })} /></label>
          <label>Initial password<input required type="text" minLength={8} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          <div className="wide"><button className="button primary" type="submit" disabled={creating}><UserPlus/>{creating ? "Creating…" : "Create user"}</button></div>
        </form>
        {error ? <p className="form-error">{error}</p> : null}
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h2>All users</h2><p>{users.length} accounts</p></div></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Organization</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              {users.map((user) => <tr key={user.id}>
                <td><strong>{user.full_name}</strong>{user.id === currentUser?.id ? <small> (you)</small> : null}</td>
                <td>{user.email}</td>
                <td>
                  <select value={user.role} disabled={busyId === user.id} onChange={(event) => changeRole(user, event.target.value as Role)}>
                    {user.role === "originator" ? <option value="originator">Originator</option> : null}
                    {ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </td>
                <td>{user.organization ?? "—"}</td>
                <td><span className={`state-badge ${user.is_active ? "state-live" : "state-stub"}`}>{user.is_active ? "Active" : "Deactivated"}</span></td>
                <td><small>{new Date(user.created_at).toISOString().slice(0, 10)}</small></td>
                <td>
                  <button
                    className="button secondary"
                    disabled={busyId === user.id || user.id === currentUser?.id}
                    onClick={() => toggleActive(user)}
                    title={user.id === currentUser?.id ? "You cannot deactivate your own account" : undefined}
                  >
                    {user.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
