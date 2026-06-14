import { useId, useState } from 'react';
import { Info } from 'lucide-react';
import { cn } from '../../lib/utils';
import { TABLE_INFO, type TableInfoContent, type TableInfoId } from './tableInfoContent';

type TableInfoDialogProps = {
  content: TableInfoContent;
  tableId: TableInfoId;
  titleId: string;
  onClose: () => void;
};

function TableInfoDialogPanel({ content, tableId, titleId, onClose }: TableInfoDialogProps) {
  return (
    <div className="modal-root" role="presentation">
      <button type="button" className="modal-backdrop" aria-label="Close dialog" onClick={onClose} />
      <div
        className="info-dialog-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="info-dialog-head">
          <div>
            <h2 id={titleId} className="info-dialog-title">
              {content.title}
            </h2>
            <p className="info-dialog-subtitle">{tableId}</p>
          </div>
          <button
            type="button"
            className="info-dialog-close"
            aria-label="Close dialog"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className="info-dialog-body">
          <section className="info-dialog-section">
            <p className="info-dialog-label">What this measures</p>
            <p className="info-dialog-value">{content.measures}</p>
          </section>

          <section className="info-dialog-section">
            <p className="info-dialog-label">Column definitions</p>
            <div className="info-dialog-table">
              <table aria-label="Column definitions">
                <thead>
                  <tr>
                    <th scope="col">Column</th>
                    <th scope="col">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {content.columns.map((col) => (
                    <tr key={col.name}>
                      <td className="info-dialog-col-name">{col.name}</td>
                      <td className="info-dialog-col-desc">{col.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="info-dialog-section">
            <p className="info-dialog-label">How to analyze</p>
            <div className="info-dialog-analysis">
              {content.analysis.map((block, index) =>
                block.kind === 'paragraph' ? (
                  <p key={`analysis-p-${index}`} className="info-dialog-value">
                    {block.text}
                  </p>
                ) : (
                  <ul key={`analysis-l-${index}`} className="info-dialog-list">
                    {block.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )
              )}
            </div>
          </section>
        </div>

        <div className="info-dialog-actions">
          <button type="button" className="btn btn--primary" onClick={onClose}>
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
          tableId={tableId}
          titleId={titleId}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
