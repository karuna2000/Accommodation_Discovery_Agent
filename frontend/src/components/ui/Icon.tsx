import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface IconProps {
  name: string;
  size?: number | string;
  fill?: boolean;
  className?: string;
  weight?: number;
  children?: ReactNode;
}

export function Icon({ name, size = 20, fill = false, className, weight }: IconProps) {
  return (
    <span
      className={cn("material-symbols-outlined select-none", className)}
      style={{
        fontSize: size,
        fontVariationSettings: `'FILL' ${fill ? 1 : 0}, 'wght' ${weight ?? (fill ? 400 : 300)}`,
      }}
      aria-hidden
    >
      {name}
    </span>
  );
}
