import { useState, useEffect, useCallback } from "react";
import { getLeaderboard, type LeaderboardEntry as APIEntry } from "../api";

interface LeaderboardProps {
  title: string;
  highlightUserId?: string;
}

function formatDuration(ms: number): string {
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const centiseconds = Math.floor((ms % 1000) / 10);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}:${String(centiseconds).padStart(2, "0")}`;
}

export function Leaderboard({ title, highlightUserId }: LeaderboardProps) {
  const [entries, setEntries] = useState<APIEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const data = await getLeaderboard();
      setEntries(data.entries);
    } catch (err) {
      console.error("Failed to fetch leaderboard:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="border-2 md:border-4 border-[#3A3A3A] bg-[#1A1A1A]">
      {/* Header */}
      <div className="bg-[#F5F5F5] text-[#121212] p-3 md:p-4 border-b-2 md:border-b-4 border-[#3A3A3A]">
        <h3
          className="text-base md:text-xl font-bold uppercase tracking-wider"
          style={{ fontWeight: 700, fontFamily: "'Space Grotesk', sans-serif" }}
        >
          {title}
        </h3>
      </div>

      {/* Column Headers - Hidden on mobile, shown on desktop */}
      <div className="hidden md:grid grid-cols-[auto_1fr_auto_auto] gap-4 p-4 border-b-2 border-[#3A3A3A] bg-[#0A0A0A]">
        <div
          className="text-xs uppercase tracking-wider opacity-70 w-12"
          style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}
        >
          Rank
        </div>
        <div
          className="text-xs uppercase tracking-wider opacity-70"
          style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}
        >
          Player
        </div>
        <div
          className="text-xs uppercase tracking-wider opacity-70 text-right w-28"
          style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}
        >
          Time
        </div>
        <div
          className="text-xs uppercase tracking-wider opacity-70 text-right w-24"
          style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}
        >
          Date
        </div>
      </div>

      {/* Entries */}
      <div className="divide-y-2 divide-[#2A2A2A]">
        {isLoading ? (
          <div className="p-8 text-center">
            <p
              className="text-sm opacity-50 uppercase tracking-wider"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              Loading...
            </p>
          </div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center">
            <p
              className="text-sm opacity-50 uppercase tracking-wider"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              No players yet — be the first!
            </p>
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.rank}
              className={`p-3 md:p-4 hover:bg-[#2A2A2A] transition-colors ${highlightUserId === entry.user_id
                  ? "bg-[#FF3333]/20 border-l-2 md:border-l-4 border-[#FF3333]"
                  : ""
                }`}
            >
              {/* Mobile Layout */}
              <div className="md:hidden flex items-center justify-between gap-3">
                {/* Left: Rank + Player */}
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div
                    className="text-base font-bold tabular-nums flex-shrink-0"
                    style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}
                  >
                    {entry.rank}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div
                      className="text-sm truncate"
                      style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}
                    >
                      {entry.username}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className="text-xs opacity-70"
                        style={{ fontFamily: "'JetBrains Mono', monospace" }}
                      >
                        {entry.date}
                      </span>
                    </div>
                  </div>
                </div>
                {/* Right: Time */}
                <div
                  className="text-sm font-bold tabular-nums flex-shrink-0"
                  style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}
                >
                  {formatDuration(entry.duration_ms)}
                </div>
              </div>

              {/* Desktop Layout */}
              <div className="hidden md:grid grid-cols-[auto_1fr_auto_auto] gap-4 items-center">
                {/* Rank */}
                <div
                  className="text-xl font-bold tabular-nums w-12"
                  style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}
                >
                  {entry.rank}
                </div>

                {/* Username */}
                <div
                  className="text-base truncate"
                  style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600 }}
                >
                  {entry.username}
                </div>

                {/* Time */}
                <div
                  className="text-base font-bold tabular-nums text-right w-28"
                  style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}
                >
                  {formatDuration(entry.duration_ms)}
                </div>

                {/* Date */}
                <div
                  className="text-sm opacity-70 tabular-nums text-right w-24"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {entry.date}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer Note */}
      <div className="p-3 md:p-4 border-t-2 md:border-t-4 border-[#3A3A3A] bg-[#0A0A0A]">
        <p
          className="text-xs opacity-50 uppercase tracking-wider"
          style={{ fontFamily: "'JetBrains Mono', monospace" }}
        >
          All-Time Rankings - Updates every 30 seconds
        </p>
      </div>
    </div>
  );
}