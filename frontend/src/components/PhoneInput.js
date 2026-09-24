import React from "react";
import { Input } from "./ui";
import { normalizePhone } from "../lib/phone";

export const PhoneInput = React.forwardRef(function PhoneInput({ value, onChange, ...props }, ref) {
  return (
    <Input
      ref={ref}
      type="tel"
      inputMode="tel"
      autoComplete="tel-national"
      maxLength={20}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={() => {
        const canonical = normalizePhone(value);
        if (canonical && canonical !== value) onChange(canonical);
      }}
      {...props}
    />
  );
});
