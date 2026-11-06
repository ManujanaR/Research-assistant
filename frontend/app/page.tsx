export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Mitra Research Assistant
        </h1>
        <p className="mt-4 text-base text-slate-600">
          Upload a research paper to generate a 5-section structured summary and ask grounded questions.
        </p>
      </div>
    </main>
  );
}
