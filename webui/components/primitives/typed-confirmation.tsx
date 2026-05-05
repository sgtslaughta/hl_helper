'use client';

import { useEffect, useState } from 'react';

interface Props {
  expected: string;
  onMatch: (match: boolean) => void;
  placeholder?: string;
}

export function TypedConfirmation({ expected, onMatch, placeholder }: Props) {
  const [value, setValue] = useState('');
  useEffect(() => {
    onMatch(value === expected);
  }, [value, expected, onMatch]);
  return (
    <label className="block text-sm text-text-dim">
      Type <code className="text-text">{expected}</code> to confirm:
      <input
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder={placeholder ?? expected}
        className="mt-1 w-full rounded border border-hairline bg-surface px-2 py-1 font-mono text-text"
        autoComplete="off"
        spellCheck={false}
      />
    </label>
  );
}
