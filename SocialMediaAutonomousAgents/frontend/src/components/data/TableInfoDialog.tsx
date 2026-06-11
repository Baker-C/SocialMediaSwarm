import { useId, useState } from 'react';
import { Info } from 'lucide-react';
import { cn } from '../../lib/utils';
import { TABLE_INFO, type TableInfoContent, type TableInfoId } from './tableInfoContent';

type TableInfoDialogProps = {
  content: TableInfoContent;
  titleId: string;
  onClose: () => void;
};

function TableInfoDialogPanel({ content, titleId, onClose }: TableInfoDialogProps) {
  return (
    <div className="modal-root" role="presentation">
      <button type="button" className="modal-backdrop" aria-label="Close dialog" onClick={onClose} />
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="modal-head">
          <h2 id={titleId}>{content.title}</h2>
        </header>

        <div className="space-y-5 px-[18px] py-4 font-mono text-sm leading-relaxed text-neutral-300">
          <section>
            <h3 className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-orange-500">
              What this measures
            </h3>
            <p className="m-0">{content.measures}</p>
          </section>

          <section>
            <h3 className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-orange-500">
              Column definitions
            </h3>
            <dl className="m-0 space-y-3">
              {content.columns.map((col) => (
                <div key={col.name}>
                  <dt className="font-semibold text-neutral-100">{col.name}</dt>
                  <dd className="ml-0 mt-0.5 text-neutral-400">{col.description}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-orange-500">
              How to analyze
            </h3>
            <p className="m-0">{content.analysis}</p>
          </section>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

type TableInfoButtonProps = {
  tableId: TableInfoId;
  className?: string;
};

export function TableInfoButton({ tableId, className }: TableInfoButtonProps) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const content = TABLE_INFO[tableId];

  return (
    <>
      <button
        type="button"
        className={cn(
          'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-neutral-700 bg-transparent text-neutral-400 transition-colors hover:border-orange-500 hover:text-orange-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/50',
          className
        )}
        aria-label={`About ${content.title}`}
        onClick={() => setOpen(true)}
      >
        <Info size={15} aria-hidden />
      </button>
      {open ? (
        <TableInfoDialogPanel
          content={content}
          titleId={titleId}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
