type EmptyStateProps = {
  title?: string;
  message: string;
};

export function EmptyState({ title, message }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      {title ? <p className="empty-state__title">{title}</p> : null}
      <p className="empty-state__message">{message}</p>
    </div>
  );
}
