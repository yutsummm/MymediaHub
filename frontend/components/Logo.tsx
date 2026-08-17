/**
 * Знак «медиаПространство» — округлый геометрический строчный плюс искра.
 *
 * Единственный источник правды. До этого один и тот же SVG лежал шестью
 * дословными копиями (сайдбар, вход, регистрация, восстановление пароля,
 * приглашение, создание группы) — правку пришлось бы вносить в каждую.
 *
 * Надпись — настоящий текст, а не контуры в SVG: она наследует цвет через
 * `currentColor`, читается скринридером и поиском по странице, и её не надо
 * пересобирать при смене шрифта. Искра — inline SVG: восемь точек звезды
 * контуром описываются точнее, чем чем-либо ещё, и масштабируются вместе с
 * кеглем, потому что размеры заданы в `em`.
 */

/** Четырёхлучевая звезда в квадрате 100×100. Вершины дают тонкую «щепотку» у центра. */
const STAR = '50,0 59,41 100,50 59,59 50,100 41,59 0,50 41,41'

/**
 * Искра: крупная звезда снизу-слева, мелкая сверху-справа.
 * Пропорции взяты из макета (звёзды 30 и 14 в поле 40) и переведены в em,
 * поэтому знак остаётся собой на любом кегле.
 */
function Spark({ style }: { style?: React.CSSProperties }) {
  return (
    <svg
      viewBox="0 0 40 40"
      width="0.77em"
      height="0.77em"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      style={{ flex: 'none', marginTop: '-0.23em', ...style }}
    >
      <polygon points={STAR} transform="translate(0 4) scale(0.3)" />
      <polygon points={STAR} transform="translate(26 0) scale(0.14)" />
    </svg>
  )
}

export type LogoProps = {
  /** Кегль надписи в пикселях; всё остальное считается от него. */
  size?: number
  /** Подпись под знаком. Без неё знак остаётся самостоятельным. */
  subtitle?: string
  className?: string
  style?: React.CSSProperties
}

export default function Logo({ size = 20, subtitle, className, style }: LogoProps) {
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        minWidth: 0,
        ...style,
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'flex-start',
          gap: '0.115em',
          fontFamily: 'var(--font-display), system-ui, sans-serif',
          fontWeight: 600,
          fontSize: size,
          lineHeight: 1,
          letterSpacing: '-0.02em',
          whiteSpace: 'nowrap',
        }}
      >
        {/* «медиа» плотнее «Пространства» — вес разводит две части названия
            без пробела и без второго цвета. */}
        <span>
          медиа<span style={{ fontWeight: 400 }}>Пространство</span>
        </span>
        <Spark />
      </span>
      {subtitle && (
        <span
          style={{
            fontSize: Math.max(8, size * 0.42),
            lineHeight: 1.3,
            letterSpacing: '0.02em',
            opacity: 0.5,
            marginTop: size * 0.18,
            whiteSpace: 'nowrap',
          }}
        >
          {subtitle}
        </span>
      )}
    </span>
  )
}

/**
 * Одна искра без надписи — для аватара, фавикона и мест, где на слово нет ширины.
 * Точечная матрица повторяет фон основного знака в макете.
 */
export function LogoMark({ size = 40, dots = true }: { size?: number; dots?: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'grid',
        placeItems: 'center',
        position: 'relative',
        width: size,
        height: size,
        borderRadius: '50%',
        overflow: 'hidden',
        background: '#0f0f0f',
        color: '#fff',
        flex: 'none',
      }}
    >
      {dots && (
        <span
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: 'radial-gradient(rgba(255,255,255,0.35) 0.9px, transparent 1px)',
            backgroundSize: `${Math.max(4, size * 0.14)}px ${Math.max(4, size * 0.14)}px`,
          }}
        />
      )}
      <svg
        viewBox="0 0 100 100"
        width={size * 0.54}
        height={size * 0.54}
        fill="currentColor"
        style={{ position: 'relative' }}
      >
        <polygon points={STAR} />
      </svg>
    </span>
  )
}
