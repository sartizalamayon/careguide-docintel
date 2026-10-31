"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

const KEY = "docintel.reviewer";

/** The reviewer's name: the one typed last time, else the signed-in Google name. */
export function useReviewer(): [string, (name: string) => void] {
  const [name, setName] = useState("");
  const sessionName = useSession().data?.user?.name ?? "";

  useEffect(() => {
    let stored = "";
    try {
      stored = window.localStorage.getItem(KEY) ?? "";
    } catch {
      stored = "";
    }
    setName(stored || sessionName);
  }, [sessionName]);

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
