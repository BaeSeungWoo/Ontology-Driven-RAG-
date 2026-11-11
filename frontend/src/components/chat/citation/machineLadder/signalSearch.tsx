import { useId, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import type { MachineLadderNet } from "@/services/ladderApi";
import styles from "../citation.module.css";

type Option = { value: string; label: string; net?: MachineLadderNet };

export default function SignalSearch({ addresses, locations, onSearch, onCircuitSelect }: {
  addresses: ReadonlySet<string>; locations: { label: string; net: MachineLadderNet }[];
  onSearch: (address: string) => void; onCircuitSelect: (net: MachineLadderNet, description: string) => void;
}) {
  const addressOptions = useMemo(() => [...addresses].sort(new Intl.Collator("en", { numeric: true }).compare)
    .map(address => ({ value: address, label: address })), [addresses]);
  const descriptions = useMemo(() => locations.flatMap(({ label, net }) => {
    const coils = net.outputs.flatMap(output => output.type === "function" ? output.coils ?? [] : [output]);
    const comments = new Set(coils.map(coil => coil.comment?.trim()).filter(Boolean));
    return [...comments].flatMap(value => value ? [{ value, net, label: `${value} · ${label} · RUNG ${String(net.netIndex).padStart(3, "0")}` }] : []);
  }), [locations]);
  return <>
    <SearchField options={addressOptions} onSearch={option => onSearch(option.value)} />
    <SearchField options={descriptions} byDescription onSearch={option => { if (option.net) onCircuitSelect(option.net, option.value); }} />
  </>;
}

function SearchField({ options, byDescription = false, onSearch }: {
  options: Option[]; byDescription?: boolean; onSearch: (option: Option) => void;
}) {
  const listId = useId();
  const list = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const prefix = query.trim().toUpperCase();
  const matches = options.filter(option => byDescription ? option.value.toUpperCase().includes(prefix) : option.value.startsWith(prefix));
  const name = byDescription ? "회로 설명" : "신호 주소";
  const input = useRef<HTMLInputElement>(null);

  function close() {
    setOpen(false);
    setActive(-1);
  }
  function search(option: Option) {
    setQuery(option.value);
    close();
    onSearch(option);
  }

  return <form className={styles.ladderSignalSearch} role="search" aria-label={`장비 전체 ${name} 검색`}
    onSubmit={event => {
      event.preventDefault();
      if (byDescription && matches.length !== 1) {
        input.current?.focus();
        setOpen(true);
      } else if (prefix) search(byDescription ? matches[0] : { value: prefix, label: prefix });
    }}>
    <input ref={input} type="search" role="combobox" aria-label={name} placeholder={byDescription ? "회로 설명 검색 (예: INTERLOCK)" : "신호 주소 검색 (예: X5.5)"}
      required autoComplete="off" value={query} aria-autocomplete="list" aria-expanded={open}
      aria-controls={open ? listId : undefined} aria-activedescendant={open && active >= 0 ? listId + active : undefined}
      onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onBlur={close}
      onChange={event => { setQuery(event.target.value); setActive(-1); setOpen(true); }}
      onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          setOpen(true);
          if (!matches.length) return;
          const next = event.key === "ArrowDown" ? Math.min(active + 1, matches.length - 1)
            : active < 0 ? matches.length - 1 : Math.max(active - 1, 0);
          setActive(next);
          list.current?.children[next]?.scrollIntoView?.({ block: "nearest" });
        } else if (open && event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          close();
        } else if (open && active >= 0 && event.key === "Enter") {
          event.preventDefault();
          search(matches[active]);
        }
      }} />
    <button type="submit" aria-label={byDescription ? "회로 설명 검색" : "신호 검색"} title={byDescription ? "회로 설명 검색" : "신호 검색"}><Search size={16} aria-hidden="true" /></button>
    {open && <ul id={listId} ref={list} className={styles.signalOptions} role="listbox" aria-label={`${name} 목록`}
      onMouseDown={event => event.preventDefault()}>
      {matches.map((option, index) => <li key={option.label} id={listId + index} role="option"
        aria-selected={index === active} onClick={() => search(option)}>{option.label}</li>)}
      {!matches.length && <li role="presentation">{byDescription ? "일치하는 회로 설명이 없습니다." : "일치하는 신호가 없습니다."}</li>}
    </ul>}
  </form>;
}
