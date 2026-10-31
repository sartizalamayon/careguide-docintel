"use client";

import { useEffect, useState } from "react";

const KEY = "docintel.reviewer";

export function useReviewer(): [string, (name: string) => void] {
  const [name, setName] = useState("");

  useEffect(() => {
    try {
      setName(window.localStorage.getItem(KEY) ?? "");
    } catch {
      setName("");
    }
  }, []);

  const remember = (value: string) => {
    setName(value);
    try {
      window.localStorage.setItem(KEY, value);
    } catch {
      // storage unavailable: the name is kept for this visit only
    }
  };

  return [name, remember];
}
