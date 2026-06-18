import { useState, type FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { login } from '../../api/auth';
import { Sigil } from '../../components/brand/Sigil';

type LoginPageProps = {
  onAuthed: () => void;
};

export function LoginPage({ onAuthed }: LoginPageProps) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(password);
      onAuthed();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-hero">
      <h1 className="login-hero-wordmark" aria-label="Solomon's Swarm">
        <span className="login-word login-word--solomon">SOLOMON&apos;S</span>
        <span className="login-word login-word--swarm">SWARM</span>
      </h1>

      <div className="login-hero-stage">
        <div className="login-hero-sigil">
          <Sigil size={300} />
        </div>

        <form className="login-hero-form" onSubmit={handleSubmit}>
        <div className={`login-hero-field ${error ? 'login-hero-field--error' : ''}`}>
          <input
            className="login-hero-input"
            type="password"
            autoFocus
            autoComplete="current-password"
            placeholder="ENTER PASSPHRASE"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-label="Passphrase"
          />
          <button
            className="login-hero-submit"
            type="submit"
            disabled={submitting || !password}
            aria-label="Enter"
          >
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
        {error ? (
          <div className="login-hero-error" role="alert">
            {error}
          </div>
        ) : null}
        </form>
      </div>
    </div>
  );
}
