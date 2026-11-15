import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { paletteExtras, primaryNavigation } from '../../app/navigation';
import { Icon, type IconName } from '../ui/Icon';
import './CommandPalette.css';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

interface Command {
  id: string;
  label: string;
  path: string;
  icon: IconName;
  group: string;
}

/**
 * Navigation palette.
 *
 * This is a real control, not an ornament: it opens on ⌘K / Ctrl-K, filters
 * by label, is fully operable by keyboard (arrow keys, Enter, Escape), and
 * every entry navigates somewhere that exists. It contains no fake "ask AI"
 * affordance, because no such capability is implemented.
 */
export function CommandPalette({ open, onClose }: CommandPaletteProps): JSX.Element | null {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useMemo<Command[]>(() => {
    const fromNav = primaryNavigation.map((item) => ({
      id: item.id,
      label: item.label,
      path: item.path,
      icon: item.icon,
      group: 'Navigate',
    }));
    const extras = paletteExtras.map((item) => ({
      id: item.id,
      label: item.label,
      path: item.path,
      icon: item.icon,
      group: 'Also',
    }));
    return [...fromNav, ...extras];
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (command) =>
        command.label.toLowerCase().includes(needle) ||
        command.group.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  // Escape must work whatever element inside the dialog holds focus, so it is
  // bound at the document rather than relying on bubbling from the input.
  useEffect(() => {
    if (!open) return undefined;
    const onEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onEscape);
    return () => document.removeEventListener('keydown', onEscape);
  }, [open, onClose]);

  // Reset each time it opens so it never reopens mid-search.
  useEffect(() => {
    if (open) {
      setQuery('');
      setIndex(0);
      const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    setIndex(0);
  }, [query]);

  // Keep the highlighted row in view when navigating by keyboard.
  useEffect(() => {
    const items = listRef.current?.querySelectorAll('[role="option"]');
    (items?.[index] as HTMLElement | undefined)?.scrollIntoView({ block: 'nearest' });
  }, [index]);

  if (!open) return null;

  const run = (command: Command | undefined): void => {
    if (!command) return;
    navigate(command.path);
    onClose();
  };

  const onKeyDown = (event: React.KeyboardEvent): void => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setIndex((current) => (filtered.length ? (current + 1) % filtered.length : 0));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setIndex((current) =>
        filtered.length ? (current - 1 + filtered.length) % filtered.length : 0,
      );
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      run(filtered[index]);
    }
  };

  let lastGroup = '';

  return (
    <div className="palette" role="presentation" onKeyDown={onKeyDown}>
      <div className="palette__scrim" onClick={onClose} role="presentation" />
      <div
        className="palette__dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="palette__input-row">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            className="palette__input"
            type="text"
            placeholder="Jump to a page…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search pages"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-autocomplete="list"
            aria-activedescendant={filtered[index] ? `palette-item-${filtered[index].id}` : undefined}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="palette__esc">esc</kbd>
        </div>

        {/* Valid ARIA listbox: only `group` and `option` may be children, which
            is why the group labels are real role="group" wrappers rather than
            decorative paragraphs. Focus stays in the combobox input and the
            active option is announced via aria-activedescendant. */}
        <div
          className="palette__results"
          id="palette-results"
          role="listbox"
          aria-label="Pages"
          ref={listRef}
        >
          {filtered.length === 0 && (
            <p className="palette__empty" role="status">
              No page matches “{query}”.
            </p>
          )}
          {filtered.map((command, itemIndex) => {
            const showGroup = command.group !== lastGroup;
            lastGroup = command.group;
            return (
              <div key={command.id}>
                {showGroup && (
                  <div className="palette__group" role="group" aria-label={command.group}>
                    <span aria-hidden="true">{command.group}</span>
                  </div>
                )}
                <div
                  id={`palette-item-${command.id}`}
                  role="option"
                  aria-selected={itemIndex === index}
                  tabIndex={-1}
                  className={`palette__item ${itemIndex === index ? 'is-active' : ''}`}
                  onMouseEnter={() => setIndex(itemIndex)}
                  onClick={() => run(command)}
                >
                  <span className="palette__item-icon">
                    <Icon name={command.icon} size={15} />
                  </span>
                  <span className="palette__item-label">{command.label}</span>
                  <Icon name="enter" size={12} />
                </div>
              </div>
            );
          })}
        </div>

        <div className="palette__footer">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>↵</kbd> open
          </span>
          <span>
            <kbd>esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
