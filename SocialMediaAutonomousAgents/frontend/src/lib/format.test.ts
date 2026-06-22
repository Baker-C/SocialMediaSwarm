import { buildXProfileUrl } from './format';

describe('buildXProfileUrl', () => {
  it('prefers the numeric id (immune to username changes)', () => {
    expect(buildXProfileUrl({ xUserId: '2054643922534875136', xUsername: 'someone' })).toBe(
      'https://x.com/i/user/2054643922534875136'
    );
  });

  it('falls back to a validated username when no id', () => {
    expect(buildXProfileUrl({ xUsername: 'jack' })).toBe('https://x.com/jack');
  });

  it('strips a leading @ from the username', () => {
    expect(buildXProfileUrl({ xUsername: '@jack' })).toBe('https://x.com/jack');
  });

  it('trims surrounding whitespace from the username', () => {
    expect(buildXProfileUrl({ xUsername: '  jack  ' })).toBe('https://x.com/jack');
  });

  it('returns null for a blank username', () => {
    expect(buildXProfileUrl({ xUsername: '   ' })).toBeNull();
  });

  it('returns null for a username with spaces', () => {
    expect(buildXProfileUrl({ xUsername: 'foo bar' })).toBeNull();
  });

  it('returns null for a pasted profile URL', () => {
    expect(buildXProfileUrl({ xUsername: 'https://x.com/jack' })).toBeNull();
  });

  it('returns null for a username longer than 15 chars', () => {
    expect(buildXProfileUrl({ xUsername: 'a'.repeat(16) })).toBeNull();
  });

  it('returns null when both id and username are absent', () => {
    expect(buildXProfileUrl({})).toBeNull();
    expect(buildXProfileUrl({ xUserId: null, xUsername: null })).toBeNull();
  });

  it('never produces i/user/null', () => {
    expect(buildXProfileUrl({ xUserId: null, xUsername: 'jack' })).toBe('https://x.com/jack');
    expect(buildXProfileUrl({ xUserId: '  ', xUsername: 'jack' })).toBe('https://x.com/jack');
  });
});
