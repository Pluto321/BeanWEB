import React, { useEffect, useRef, useState } from 'react';

type Props = {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
};

/** 可搜索账户选择框：输入过滤 + 下拉展示，允许自由输入（新账户名） */
export const AccountCombobox = ({ value, onChange, options, placeholder = '输入或选择账户', disabled, style }: Props) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(value);
  const boxRef = useRef<HTMLDivElement>(null);
  const internalChange = useRef(false);

  useEffect(() => {
    if (!internalChange.current) setText(value);
    internalChange.current = false;
  }, [value]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = text
    ? options.filter(o => o.toLowerCase().includes(text.toLowerCase()))
    : options;

  return (
    <div ref={boxRef} style={{ position: 'relative', flex: 1, ...style }}>
      <input
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={e => {
          setText(e.target.value);
          setOpen(true);
          internalChange.current = true;
          onChange(e.target.value);
        }}
        style={{ width: '100%' }}
      />
      {open && (
        <div className="combobox-menu">
          {options.length === 0 && <div className="combobox-item muted">暂无账户，可在账户管理中新增</div>}
          {filtered.length === 0 && options.length > 0 && (
            <div className="combobox-item muted">无匹配，将使用输入值"{text}"</div>
          )}
          {filtered.map(o => (
            <div
              key={o}
              className={`combobox-item ${o === value ? 'active' : ''}`}
              onClick={() => {
                setText(o);
                onChange(o);
                setOpen(false);
              }}
            >
              {o}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
