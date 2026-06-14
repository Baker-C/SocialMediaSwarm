import { cn } from '../../lib/utils';
import { TableInfoButton } from './TableInfoDialog';
import type { TableInfoId } from './tableInfoContent';

type TablePanelHeaderProps = {
  title: string;
  tableId: TableInfoId;
  titleClassName?: string;
};

export function TablePanelHeader({ title, tableId, titleClassName }: TablePanelHeaderProps) {
  return (
    <div className="mb-3 flex w-full items-center justify-between gap-2">
      <h3 className={cn('hq-panel__title mb-0', titleClassName)}>{title}</h3>
      <TableInfoButton tableId={tableId} />
    </div>
  );
}
