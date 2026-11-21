// The MARG milestone emblem (vectorised from assets/main logo.jpeg) beside the product wordmark.
// At header size the emblem's own lettering is too small to read, so the wordmark carries the name.
export default function Logo() {
  return (
    <span className="flex shrink-0 items-center gap-2.5">
      <img src="/brand/marg-mark.svg" alt="" width={38} height={40} className="h-10 w-[38px]" />
      <span className="text-base font-bold tracking-tight">MARG·LEDGER</span>
    </span>
  )
}
