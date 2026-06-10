type ErrorBannerProps = {
  title?: string;
  message: string;
  details?: string[];
};

export function ErrorBanner({ title, message, details }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      {title ? <p className="error-banner__title">{title}</p> : null}
      <p className="error">{message}</p>
      {details && details.length > 0 ? (
        <ul className="error-banner__list">
          {details.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
