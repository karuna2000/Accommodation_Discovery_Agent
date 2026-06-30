import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassPanelProps {
  children: ReactNode;
  className?: string;
  as?: "div" | "button";
  onClick?: () => void;
}

export function GlassPanel({ children, className, as: Tag = "div", onClick }: GlassPanelProps) {
  return (
    <Tag
      className={cn("glass-hud rounded-xl", className)}
      onClick={onClick}
    >
      {children}
    </Tag>
  );
}
