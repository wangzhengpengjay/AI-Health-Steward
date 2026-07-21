interface PagePlaceholderProps {
  icon: string
  title: string
  description: string
}

// Shared skeleton for pages not yet implemented in current version
export default function PagePlaceholder({
  icon,
  title,
  description,
}: PagePlaceholderProps) {
  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="mb-6 flex items-center gap-3">
        <span className="material-symbols-rounded text-3xl text-primary">
          {icon}
        </span>
        <h1 className="text-2xl font-semibold text-slate-800">{title}</h1>
      </div>

      <div className="rounded-card border border-slate-200 bg-bg-primary p-12">
        <div className="flex flex-col items-center justify-center text-center">
          <span className="material-symbols-rounded mb-4 text-5xl text-slate-300">
            schedule
          </span>
          <h2 className="mb-2 text-lg font-medium text-slate-600">即将上线</h2>
          <p className="max-w-md text-sm text-slate-400">{description}</p>
        </div>
      </div>
    </div>
  )
}
