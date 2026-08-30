"use client";

import React, { useEffect, useState } from "react";

interface UtcDateTimeInputProps {
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  className?: string;
}

/**
 * Aviation-grade 24-hour UTC DateTime Input component.
 *
 * Solves the issue where browser `datetime-local` inputs enforce 12-hour AM/PM
 * on Windows systems and prevent typing 24-hour UTC military times like `23:00`, `23:59`.
 *
 * Automatically splits and syncs `YYYY-MM-DD` (Date) and `HH:MM` (24h UTC Time).
 * Auto-formats `2300` -> `23:00` on typing.
 */
export function UtcDateTimeInput({
  value = "",
  onChange,
  disabled = false,
  required = false,
  id,
  className = "",
}: UtcDateTimeInputProps) {
  // Parse incoming value into date (YYYY-MM-DD) and time (HH:MM)
  const parseValue = (val: string): { date: string; time: string } => {
    if (!val) return { date: "", time: "" };
    // Handle formats like "2026-07-17T19:00:00Z", "2026-07-17T19:00", "2026-07-17 19:00"
    const cleaned = val.replace("Z", "").trim();
    if (cleaned.includes("T")) {
      const [d, t] = cleaned.split("T");
      return { date: d || "", time: (t || "").slice(0, 5) };
    }
    if (cleaned.includes(" ")) {
      const [d, t] = cleaned.split(" ");
      return { date: d || "", time: (t || "").slice(0, 5) };
    }
    return { date: cleaned, time: "" };
  };

  const parsed = parseValue(value);
  const [datePart, setDatePart] = useState(parsed.date);
  const [timePart, setTimePart] = useState(parsed.time);

  useEffect(() => {
    const next = parseValue(value);
    setDatePart(next.date);
    setTimePart(next.time);
  }, [value]);

  const emitCombined = (d: string, t: string) => {
    if (!d && !t) {
      onChange?.("");
      return;
    }
    if (d && !t) {
      onChange?.(`${d}T00:00`);
      return;
    }
    if (d && t) {
      // Ensure time is padded (e.g. 9:00 -> 09:00)
      let formattedTime = t;
      if (/^\d{1,2}:\d{2}$/.test(t)) {
        const [h, m] = t.split(":");
        formattedTime = `${h.padStart(2, "0")}:${m}`;
      }
      onChange?.(`${d}T${formattedTime}`);
    }
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setDatePart(newDate);
    emitCombined(newDate, timePart);
  };

  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let raw = e.target.value.trim();

    // If user enters 4 digits without colon (e.g., "2300" -> "23:00")
    if (/^\d{4}$/.test(raw)) {
      raw = `${raw.slice(0, 2)}:${raw.slice(2, 4)}`;
    }

    setTimePart(raw);
    emitCombined(datePart, raw);
  };

  const handleTimeBlur = () => {
    if (!timePart) return;
    let formatted = timePart.trim();
    // Auto-fix 3-4 digits on blur like "700" -> "07:00", "2300" -> "23:00"
    if (/^\d{3}$/.test(formatted)) {
      formatted = `0${formatted[0]}:${formatted.slice(1, 3)}`;
    } else if (/^\d{4}$/.test(formatted)) {
      formatted = `${formatted.slice(0, 2)}:${formatted.slice(2, 4)}`;
    } else if (/^\d{1,2}$/.test(formatted)) {
      formatted = `${formatted.padStart(2, "0")}:00`;
    }

    // Validate 24-hour range: 00-23 and 00-59
    if (/^([01]?\d|2[0-3]):([0-5]\d)$/.test(formatted)) {
      const [h, m] = formatted.split(":");
      const normalized = `${h.padStart(2, "0")}:${m}`;
      setTimePart(normalized);
      emitCombined(datePart, normalized);
    }
  };

  return (
    <div className={`utc-datetime-input-group ${className}`} id={id}>
      <input
        type="date"
        className="utc-date-field"
        value={datePart}
        onChange={handleDateChange}
        disabled={disabled}
        required={required}
      />
      <div className="utc-time-wrapper">
        <input
          type="text"
          className="utc-time-field"
          placeholder="HH:MM"
          maxLength={5}
          value={timePart}
          onChange={handleTimeChange}
          onBlur={handleTimeBlur}
          disabled={disabled}
          required={required && !!datePart}
          pattern="^([01]?\d|2[0-3]):[0-5]\d$"
          title="24-hour UTC time (00:00 to 23:59)"
        />
        <span className="utc-zulu-badge">UTC</span>
      </div>
    </div>
  );
}
