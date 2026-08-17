import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "./status-pill";

describe("StatusPill", () => {
  it("renders an operational workflow label", () => {
    render(<StatusPill status="review" />);
    expect(screen.getByText("In review")).toBeInTheDocument();
  });
});
