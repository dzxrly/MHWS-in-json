const numbers = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
  trailingZeroDisplay: "stripIfInteger",
});

export const formatNumber = (value: number) => numbers.format(value);

// Game text embeds values in ranges and formulas. Dotted versions and identifiers stay verbatim.
export function formatDecimalText(text: string): string {
  return text.replace(/(?<![\w.])\d+\.\d+(?![\w.])/g, (value) => formatNumber(Number(value)));
}
