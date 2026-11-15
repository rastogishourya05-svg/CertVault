import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function formatBytes(n: number) {
  return n >= 1048576
    ? `${(n / 1048576).toFixed(1)} MiB`
    : `${Math.ceil(n / 1024)} KiB`;
}
